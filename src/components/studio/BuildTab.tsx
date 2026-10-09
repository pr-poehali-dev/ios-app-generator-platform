import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import Icon from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { BuildJob, fmtBytes, fmtDate, JOB_META, PHASE_LABELS, ProjectFull, studioApi } from "@/lib/studio-api";

const ACTIVE = ["pending", "running"];

const INSTALL_OPTIONS = [
  { value: "npm ci", label: "npm ci (по package-lock.json)" },
  { value: "npm install", label: "npm install" },
  { value: "pnpm install --frozen-lockfile", label: "pnpm (по pnpm-lock.yaml)" },
];

const guessInstall = (p: ProjectFull) => {
  if (p.install_cmd.startsWith("pnpm")) return "pnpm install --frozen-lockfile";
  if (p.install_cmd === "npm install") return "npm install";
  return "npm ci";
};

const guessNode = (p: ProjectFull) => {
  const m = p.node_version.match(/\d+/);
  const n = m ? Number(m[0]) : 20;
  return [18, 20, 22].includes(n) ? n : 20;
};

const JobBadge = ({ job }: { job: BuildJob }) => (
  <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${JOB_META[job.status].cls}`}>
    {JOB_META[job.status].label}
    {job.status === "running" && job.phase ? ` · ${PHASE_LABELS[job.phase] || job.phase}` : ""}
  </span>
);

const JobView = ({ jobId }: { jobId: number }) => {
  const qc = useQueryClient();
  const { data: job } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => studioApi.job(jobId),
    refetchInterval: (q) => (q.state.data && ACTIVE.includes(q.state.data.status) ? 3000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => studioApi.jobCancel(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job", jobId] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  if (!job) return <p className="text-sm text-muted-foreground">Загрузка…</p>;

  const verified = job.status === "success";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <JobBadge job={job} />
          <code className="rounded bg-secondary px-2 py-0.5 text-xs">{job.commit_sha.slice(0, 7)}</code>
          <span className="text-xs text-muted-foreground">{job.repo} · {job.branch}</span>
        </div>
        {ACTIVE.includes(job.status) && (
          <Button size="sm" variant="secondary" onClick={() => cancel.mutate()} disabled={cancel.isPending || job.cancel_requested}>
            {job.cancel_requested ? "Отмена запрошена…" : "Отменить"}
          </Button>
        )}
      </div>

      {verified && (
        <div className="flex gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          <Icon name="CircleCheck" size={16} className="mt-0.5 shrink-0" />
          <span>
            Коммит <b>{job.commit_sha.slice(0, 7)}</b> собран вне Poehali: установка и сборка завершились с кодом 0.
            {job.output_files !== null && ` В папке «${job.output_dir}» ${job.output_files} файлов, ${fmtBytes(job.output_bytes || 0)}.`}
          </span>
        </div>
      )}
      {job.error && !verified && (
        <div className="flex gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
          <Icon name="CircleX" size={16} className="mt-0.5 shrink-0" /> {job.error}
        </div>
      )}
      {job.error && verified && (
        <div className="flex gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
          <Icon name="TriangleAlert" size={16} className="mt-0.5 shrink-0" /> {job.error}
        </div>
      )}

      <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        <div>Установка: {job.install_cmd}{job.allow_scripts ? " (скрипты зависимостей разрешены)" : " (скрипты зависимостей отключены)"}</div>
        <div>Сборка: {job.build_cmd}, Node.js {job.node_major}</div>
        <div>Код возврата установки: {job.exit_install ?? "—"} · сборки: {job.exit_build ?? "—"}</div>
        <div>Создано: {fmtDate(job.created_at)}{job.finished_at ? ` · завершено: ${fmtDate(job.finished_at)}` : ""}</div>
        {job.env_info && <div className="sm:col-span-2">Среда runner: {job.env_info}</div>}
      </div>

      <div>
        <div className="mb-1 text-xs text-muted-foreground">Журнал (секреты заменены на ***)</div>
        <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-border bg-background/70 p-3 font-mono text-xs">
          {job.log || (job.status === "pending" ? "Ожидаю, пока runner заберёт задание…" : "Журнал пуст")}
        </pre>
      </div>
    </div>
  );
};

const RunnersPanel = () => {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<{ key: string; name: string } | null>(null);
  const runners = useQuery({ queryKey: ["runners"], queryFn: studioApi.runners, refetchInterval: 10000 });

  const create = useMutation({
    mutationFn: () => studioApi.runnerCreate(name || "Мой компьютер"),
    onSuccess: (r) => {
      setFresh({ key: r.key, name: r.name });
      setName("");
      qc.invalidateQueries({ queryKey: ["runners"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => studioApi.runnerRevoke(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runners"] }),
  });

  const active = (runners.data ?? []).filter((r) => !r.revoked);

  return (
    <div className="glass-card space-y-3 rounded-2xl p-5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-heading text-sm font-bold">Runner</h3>
        <span className={`text-xs ${active.some((r) => r.online) ? "text-emerald-300" : "text-muted-foreground"}`}>
          {active.some((r) => r.online) ? "на связи" : "нет runner на связи"}
        </span>
      </div>
      {active.map((r) => (
        <div key={r.id} className="flex items-center justify-between gap-2 rounded-lg border border-border px-3 py-2 text-sm">
          <div>
            <div>{r.name}</div>
            <div className="text-xs text-muted-foreground">
              {r.online ? "на связи" : r.last_seen ? `последний сигнал ${fmtDate(r.last_seen)}` : "ещё не подключался"}
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => revoke.mutate(r.id)}>Отозвать</Button>
        </div>
      ))}
      {fresh && (
        <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs">
          <p className="font-semibold text-amber-200">Ключ «{fresh.name}» показан один раз. Скопируйте его в config.json runner.</p>
          <code className="block select-all break-all rounded bg-background/70 p-2 font-mono">{fresh.key}</code>
          <Button size="sm" variant="secondary" onClick={() => { navigator.clipboard.writeText(fresh.key); toast.success("Скопировано"); }}>Копировать</Button>
          <Button size="sm" variant="ghost" onClick={() => setFresh(null)}>Я сохранил ключ</Button>
        </div>
      )}
      <div className="flex gap-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название, например: ноутбук" />
        <Button onClick={() => create.mutate()} disabled={create.isPending}>Создать ключ</Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Runner устанавливается на ваш компьютер и сам обращается в кабинет. Инструкция: docs/runner-windows.md
      </p>
    </div>
  );
};

type StartProps = { project: ProjectFull; open: boolean; onOpenChange: (v: boolean) => void; onStarted: (id: number) => void };

const StartDialog = ({ project, open, onOpenChange, onStarted }: StartProps) => {
  const qc = useQueryClient();
  const [install, setInstall] = useState(guessInstall(project));
  const [node, setNode] = useState(guessNode(project));
  const [scripts, setScripts] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const commits = useQuery({ queryKey: ["gh", project.id, "commits", project.gh_branch], queryFn: () => studioApi.ghCommits(project.id), enabled: open });
  const head = commits.data?.commits[0];

  const start = useMutation({
    mutationFn: () => studioApi.jobCreate({ id: project.id, install, node_major: node, allow_scripts: scripts, sha: head?.sha || "" }),
    onSuccess: (r) => {
      toast.success("Задание создано, ждёт runner");
      qc.invalidateQueries({ queryKey: ["jobs", project.id] });
      onOpenChange(false);
      onStarted(r.id);
    },
    onError: (e: Error) => {
      toast.error(e.message);
      qc.invalidateQueries({ queryKey: ["gh", project.id, "commits"] });
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-heading">Запустить установку и сборку</DialogTitle>
          <DialogDescription>Код репозитория и его зависимостей будет выполнен на вашем runner</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          <div className="rounded-lg border border-border p-3">
            <div className="text-xs text-muted-foreground">Репозиторий и коммит</div>
            <div className="mt-1 font-medium">{project.gh_repo} · {project.gh_branch}</div>
            {commits.isLoading && <div className="text-xs text-muted-foreground">Определяю коммит…</div>}
            {head && (
              <div className="mt-1 text-xs">
                <code className="rounded bg-secondary px-1.5 py-0.5">{head.sha.slice(0, 7)}</code> {head.message}
              </div>
            )}
            {commits.error && <div className="text-xs text-destructive">{(commits.error as Error).message}</div>}
          </div>

          <div className="space-y-1.5">
            <Label>Установка зависимостей</Label>
            <select
              value={install}
              onChange={(e) => setInstall(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {INSTALL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>Версия Node.js</Label>
            <select
              value={node}
              onChange={(e) => setNode(Number(e.target.value))}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              {[18, 20, 22].map((n) => <option key={n} value={n}>Node.js {n}{project.node_version ? "" : n === 20 ? " (по умолчанию, в проекте не указана)" : ""}</option>)}
            </select>
          </div>

          <label className="flex items-start gap-2">
            <Checkbox checked={scripts} onCheckedChange={(v) => setScripts(v === true)} className="mt-0.5" />
            <span>
              Разрешить скрипты установки зависимостей (postinstall).
              <span className="block text-xs text-muted-foreground">По умолчанию выключено: так безопаснее, но пакеты вроде esbuild или sharp иногда требуют скриптов.</span>
            </span>
          </label>

          <div className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
            <p>Сборка идёт в контейнере: без доступа к вашим файлам, без секретов, с лимитами памяти и времени, а сама сборка — без сети.</p>
            <label className="flex items-start gap-2">
              <Checkbox checked={understood} onCheckedChange={(v) => setUnderstood(v === true)} className="mt-0.5" />
              <span>Я понимаю, что будет выполнен чужой код из этого коммита, и подтверждаю запуск.</span>
            </label>
          </div>

          <Button className="w-full" disabled={!understood || !head || start.isPending} onClick={() => start.mutate()}>
            {start.isPending ? "Создаю задание…" : `Запустить для коммита ${head ? head.sha.slice(0, 7) : "…"}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const BuildTab = ({ project }: { project: ProjectFull }) => {
  const [dialog, setDialog] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const jobs = useQuery({
    queryKey: ["jobs", project.id],
    queryFn: () => studioApi.jobs(project.id),
    refetchInterval: (q) => (q.state.data?.some((j) => ACTIVE.includes(j.status)) ? 4000 : false),
  });

  const current = selected ?? jobs.data?.[0]?.id ?? null;
  const connected = Boolean(project.gh_repo);
  const busy = jobs.data?.some((j) => ACTIVE.includes(j.status));

  if (!connected) {
    return (
      <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        Сначала подключите репозиторий GitHub на вкладке «Репозиторий». Сборка запускается для конкретного коммита.
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
      <div className="space-y-4">
        <RunnersPanel />
        <div className="glass-card rounded-2xl p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-heading text-sm font-bold">Запуски</h3>
            <Button size="sm" onClick={() => setDialog(true)} disabled={busy}>
              <Icon name="Play" size={14} className="mr-1.5" /> Новая сборка
            </Button>
          </div>
          {jobs.data?.length === 0 && <p className="text-xs text-muted-foreground">Запусков ещё не было. Сборка: не проверено.</p>}
          <div className="space-y-1.5">
            {jobs.data?.map((j) => (
              <button
                key={j.id}
                onClick={() => setSelected(j.id)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-xs ${current === j.id ? "border-primary bg-primary/10" : "border-border"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <code>{j.commit_sha.slice(0, 7)}</code>
                  <JobBadge job={j} />
                </div>
                <div className="mt-1 text-muted-foreground">{fmtDate(j.created_at)}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div>
        {current ? (
          <JobView key={current} jobId={current} />
        ) : (
          <div className="rounded-xl border border-dashed border-border p-8 text-sm text-muted-foreground">
            Установка, сборка и запуск: <b className="text-foreground">не проверено</b>. Создайте ключ runner, установите runner на компьютер и запустите первую сборку.
          </div>
        )}
      </div>

      <StartDialog key={String(dialog)} project={project} open={dialog} onOpenChange={setDialog} onStarted={setSelected} />
    </div>
  );
};
