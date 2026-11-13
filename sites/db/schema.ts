import { integer, primaryKey, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const records = sqliteTable("fulfillment_records", {
  owner: text("owner").notNull(),
  id: text("id").notNull(),
  data: text("data").notNull(),
  revision: integer("revision").notNull(),
  updatedAt: text("updated_at").notNull(),
}, (table) => [primaryKey({ columns: [table.owner, table.id] })]);
