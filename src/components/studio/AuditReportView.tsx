import { useMemo, useState } from "react";
import Icon from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AuditFull, AuditStatus, Detected, fmtBytes, STATUS_META } from "@/lib/studio-api";
import { StatusBadge } from "./StatusBadge";

const ORDER: AuditStatus[] = ["needs_adaptation", "needs_setup", "unknown", "portable"];

const CONF: Record<Detected["confidence"], string> = {
  found: "найдено в файлах",
  inferred: "предположение",
  none: "не определено",
};

const CmdRow = ({ label, d }: { label: string; d: Detected }) => (
  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border py-2.5 last:border-0">
    <span className="text-sm text-muted-foreground">{label}</span>
    <div className="text-right">
      {d.value ? (
        <code className="rounded bg-secondary px-2 py-0.5 text-sm">{d.value}</code>
      ) : (
        <span className="text-sm text-slate-400">не удалось определить</span>
      )}
      <div className="mt-0.5 text-xs text-muted-foreground">
        {CONF[d.confidence]} · {d.source}
      </div>
    </div>
  </div>
);

const TreeView = ({ tree }: { tree: [string, number][] }) => {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => (q ? tree.filter(([p]) => p.toLowerCase().includes(q.toLowerCase())) : tree), [tree, q]);
  return (
    <div>
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по файлам" className="mb-3" />
      <div className="max-h-[480px] overflow-auto rounded-lg border border-border bg-background/60 p-2 font-mono text-xs">
        {filtered.slice(0, 1500).map(([p, size]) => (
          <div key={p} className="flex justify-between gap-4 rounded px-2 py-1 hover:bg-secondary">
            <span className="truncate">{p}</span>
            <span className="shrink-0 text-muted-foreground">{fmtBytes(size)}</span>
          </div>
        ))}
        {filtered.length === 0 && <div className="p-3 text-muted-foreground">Ничего не найдено</div>}
        {filtered.length > 1500 && <div className="p-3 text-muted-foreground">Показаны первые 1500 из {filtered.length}</div>}
      </div>
    </div>
  );
};

export const AuditReportView = ({ audit }: { audit: AuditFull }) => {
  const r = audit.report;
  const grouped = ORDER.map((s) => ({ s, list: r.items.filter((i) => i.status === s) })).filter((g) => g.list.length);

  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3 rounded-xl border border-border bg-secondary/40 p-4 text-sm">
        <Icon name="ShieldCheck" size={18} className="mt-0.5 shrink-0 text-primary" />
        <p className="text-muted-foreground">{r.notice} Работоспособность проекта этим отчётом не подтверждается.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        {ORDER.slice().reverse().map((s) => (
          <div key={s} className={`rounded-xl border p-4 ${STATUS_META[s].cls}`}>
            <div className="font-heading text-3xl font-black">{r.counts[s]}</div>
            <div className="text-xs">{STATUS_META[s].label}</div>
          </div>
        ))}
      </div>

      {r.warnings.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
          {r.warnings.map((w) => (
            <div key={w} className="flex gap-2">
              <Icon name="TriangleAlert" size={14} className="mt-0.5 shrink-0" /> {w}
            </div>
          ))}
        </div>
      )}

      <Tabs defaultValue="findings">
        <TabsList className="flex h-auto flex-wrap justify-start">
          <TabsTrigger value="findings">Выводы</TabsTrigger>
          <TabsTrigger value="commands">Команды</TabsTrigger>
          <TabsTrigger value="env">Переменные ({r.env_vars.length})</TabsTrigger>
          <TabsTrigger value="backend">Backend</TabsTrigger>
          <TabsTrigger value="deps">Зависимости</TabsTrigger>
          <TabsTrigger value="tree">Файлы ({audit.tree.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="findings" className="mt-4 space-y-5">
          {grouped.map(({ s, list }) => (
            <div key={s}>
              <div className="mb-2"><StatusBadge status={s} /></div>
              <div className="space-y-2">
                {list.map((it, i) => (
                  <div key={i} className="glass-card rounded-xl p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">{it.category}</span>
                      <h4 className="text-sm font-semibold">{it.title}</h4>
                    </div>
                    {it.detail && <p className="mt-1.5 text-sm text-muted-foreground">{it.detail}</p>}
                    {it.evidence.length > 0 && (
                      <ul className="mt-2 space-y-0.5 font-mono text-xs text-muted-foreground">
                        {it.evidence.map((e) => <li key={e} className="truncate">• {e}</li>)}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
          {grouped.length === 0 && <p className="text-sm text-muted-foreground">Выводов нет.</p>}
        </TabsContent>

        <TabsContent value="commands" className="mt-4">
          <div className="glass-card rounded-xl px-4">
            <CmdRow label="Менеджер пакетов" d={{ value: r.commands.package_manager, source: r.lockfiles.join(", ") || "lock-файл не найден", confidence: r.commands.package_manager ? "found" : "none" }} />
            <CmdRow label="Установка" d={r.commands.install} />
            <CmdRow label="Запуск разработки" d={r.commands.dev} />
            <CmdRow label="Сборка" d={r.commands.build} />
            <CmdRow label="Папка сборки" d={r.commands.output_dir} />
            <CmdRow label="Версия Node.js" d={r.commands.node_version} />
          </div>
          <p className="mt-3 text-xs text-muted-foreground">Команды выведены из файлов и не запускались.</p>
        </TabsContent>

        <TabsContent value="env" className="mt-4">
          {r.env_vars.length === 0 ? (
            <p className="text-sm text-muted-foreground">Обращений к переменным окружения не найдено.</p>
          ) : (
            <div className="glass-card divide-y divide-border rounded-xl">
              {r.env_vars.map((v) => (
                <div key={v.name} className="flex flex-wrap items-center justify-between gap-2 p-3">
                  <div>
                    <code className="text-sm">{v.name}</code>
                    <div className="text-xs text-muted-foreground">{v.files.join(", ")}</div>
                  </div>
                  <div className="flex gap-1.5 text-[11px]">
                    {v.likely_platform && <span className="rounded-full border border-orange-500/30 bg-orange-500/10 px-2 py-0.5 text-orange-300">задаёт платформа</span>}
                    {v.client_side && <span className="rounded-full border border-border px-2 py-0.5 text-muted-foreground">виден в браузере</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
          <p className="mt-3 text-xs text-muted-foreground">Показаны только имена. Значения не читались и не сохранялись.</p>
        </TabsContent>

        <TabsContent value="backend" className="mt-4 space-y-4">
          {r.functions.length === 0 && r.migrations.length === 0 && <p className="text-sm text-muted-foreground">Backend-функций и SQL-миграций не найдено.</p>}
          {r.functions.map((f) => (
            <div key={f.path} className="glass-card rounded-xl p-4 text-sm">
              <div className="font-semibold">{f.name} <span className="font-normal text-muted-foreground">· {f.language}</span></div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">{f.path}</div>
              <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
                <span className="rounded bg-secondary px-2 py-0.5">handler: {f.has_handler ? "найден" : "не найден"}</span>
                <span className="rounded bg-secondary px-2 py-0.5">tests.json: {f.has_tests ? "есть" : "нет"}</span>
                {f.uses_db && <span className="rounded bg-secondary px-2 py-0.5">PostgreSQL</span>}
                {f.uses_storage && <span className="rounded bg-secondary px-2 py-0.5">S3</span>}
              </div>
              {f.requirements.length > 0 && <div className="mt-2 text-xs text-muted-foreground">Пакеты: {f.requirements.join(", ")}</div>}
            </div>
          ))}
          {r.migrations.length > 0 && (
            <div className="glass-card rounded-xl p-4 text-sm">
              <div className="mb-1 font-semibold">SQL-миграции ({r.migrations.length})</div>
              <ul className="font-mono text-xs text-muted-foreground">{r.migrations.map((m) => <li key={m}>• {m}</li>)}</ul>
            </div>
          )}
        </TabsContent>

        <TabsContent value="deps" className="mt-4 grid gap-4 md:grid-cols-2">
          {([["Рабочие", r.package.prod], ["Для разработки", r.package.dev]] as const).map(([title, deps]) => (
            <div key={title} className="glass-card rounded-xl p-4">
              <div className="mb-2 text-sm font-semibold">{title} ({Object.keys(deps).length})</div>
              <div className="max-h-80 overflow-auto font-mono text-xs text-muted-foreground">
                {Object.entries(deps).map(([n, v]) => (
                  <div key={n} className="flex justify-between gap-3 py-0.5"><span className="truncate">{n}</span><span>{v}</span></div>
                ))}
                {Object.keys(deps).length === 0 && "—"}
              </div>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="tree" className="mt-4">
          <TreeView tree={audit.tree} />
        </TabsContent>
      </Tabs>
    </div>
  );
};
