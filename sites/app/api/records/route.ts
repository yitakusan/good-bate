import { env } from "cloudflare:workers";
import { getChatGPTUser } from "../../chatgpt-auth";
import { parseEntry, type Entry } from "../../../lib/fulfillment";

export const dynamic = "force-dynamic";
const reply = (data:unknown, status=200) => Response.json(data,{status,headers:{"Cache-Control":"private, no-store"}});
const decode = (row:{data:string; revision:number; updated_at:string}):Entry => ({...JSON.parse(row.data),revision:row.revision,updatedAt:row.updated_at});

export async function GET() {
  const user = await getChatGPTUser();
  if (!user) return reply({error:"请先登录 ChatGPT"},401);
  const db = env.DB;
  if (!db) return reply({error:"台账数据库暂时无法访问"},503);
  const {results} = await db.prepare("SELECT data, revision, updated_at FROM fulfillment_records WHERE owner = ? ORDER BY updated_at DESC, id").bind(user.userId).all<{data:string;revision:number;updated_at:string}>();
  return reply({entries:results.map(decode)});
}

export async function POST(request:Request) {
  const user = await getChatGPTUser();
  if (!user) return reply({error:"请先登录 ChatGPT"},401);
  const db = env.DB;
  if (!db) return reply({error:"台账数据库暂时无法访问"},503);
  const origin = request.headers.get("origin");
  if (origin !== new URL(request.url).origin || !request.headers.get("content-type")?.startsWith("application/json")) return reply({error:"请求来源无效"},403);
  let body:{action:string;entries:unknown[]};
  let entries:Entry[];
  try {
    const raw = await request.text();
    if (raw.length > 2_000_000) return reply({error:"单批数据过大，请拆分文件"},413);
    body = JSON.parse(raw);
    if (!body || !Array.isArray(body.entries) || body.entries.length < 1 || body.entries.length > 50 || !["import","save"].includes(body.action) || (body.action === "save" && body.entries.length !== 1)) return reply({error:"提交批次无效"},400);
    entries = body.entries.map(parseEntry);
    if (new Set(entries.map(e => e.id)).size !== entries.length) return reply({error:"文件内有重复记录编号"},400);
  } catch (error) {
    return reply({error:error instanceof Error ? error.message : "数据格式无效"},400);
  }
  const now = new Date().toISOString();
  const statement = (entry:Entry) => {
    const {id,kind,fields,manual,revision} = entry;
    const data = JSON.stringify({id,kind,fields,manual});
    if (body.action === "save" && revision > 0) {
      return db.prepare("UPDATE fulfillment_records SET data = ?, revision = revision + 1, updated_at = ? WHERE owner = ? AND id = ? AND revision = ? RETURNING data, revision, updated_at").bind(data,now,user.userId,id,revision);
    }
    return db.prepare("INSERT INTO fulfillment_records (owner,id,data,revision,updated_at) VALUES (?,?,?,1,?) ON CONFLICT(owner,id) DO NOTHING RETURNING data, revision, updated_at").bind(user.userId,id,data,now);
  };
  try {
    const results = await db.batch<{data:string;revision:number;updated_at:string}>(entries.map(statement));
    const saved = results.flatMap(r => r.results.map(decode));
    if (body.action === "save" && !saved.length) return reply({error:"此记录已在其他页面更新。请刷新后重新编辑。"},409);
    return reply({entries:saved,skipped:entries.length-saved.length});
  } catch {
    return reply({error:"数据库暂时无法保存，请重试"},503);
  }
}
