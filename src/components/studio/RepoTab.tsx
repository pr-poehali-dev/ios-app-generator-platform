import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import Icon from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fmtBytes, fmtDate, GhConnectResult, ProjectFull, studioApi } from "@/lib/studio-api";

type Props = { project: ProjectFull; onAudited: (auditId: number) => void };

const ConnectForm = ({ project }: { project: ProjectFull }) => {
  const qc = useQueryClient();
  const [repo, setRepo] = useState(project.gh_repo);
  const [branch, setBranch] = useState(project.gh_branch);
  const [token, setToken] = useState("");
  const [result, setResult] = useState<GhConnectResult | null>(null);

  const connect = useMutation({
    mutationFn: () =>
      studioApi.ghConnect({ id: project.id, repo, branch, token, keep_token: !token && project.gh_has_token && repo === project.gh_repo }),
    onSuccess: (r) => {
      setResult(r);
      setToken("");
      toast.success("Репозиторий подключён");
      qc.invalidateQueries({ queryKey: ["project", project.id] });
      qc.invalidateQueries({ queryKey: ["gh", project.id] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="glass-card max-w-xl space-y-4 rounded-2xl p-6">
      <div className="space-y-1.5">
        <Label>Репозиторий GitHub</Label>
        <Input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/name или https://github.com/owner/name" />
      </div>
      <div className="space-y-1.5">
        <Label>Ветка (необязательно)</Label>
        <Input value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="по умолчанию — основная ветка репозитория" />
      </div>
      <div className="space-y-1.5">
        <Label>Токен доступа (для приватных репозиториев)</Label>
        <Input
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder={project.gh_has_token ? "Сохранён. Оставьте пустым, чтобы не менять" : "github_pat_…"}
        />
        <p className="text-xs text-muted-foreground">
          Нужен fine-grained токен только на этот репозиторий с правом <b>Contents: Read-only</b>. Токен хранится в базе в зашифрованном виде и в браузер обратно не отправляется. Для публичного репозитория токен не нужен.
        </p>
      </div>
      {result?.warnings.map((w) => (
        <div key={w} className="flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          <Icon name="TriangleAlert" size={14} className="mt-0.5 shrink-0" /> {w}
        </div>
      ))}
      <Button onClick={() => connect.mutate()} disabled={connect.isPending || !repo.trim()}>
        {connect.isPending ? "Проверяю доступ…" : project.gh_repo ? "Сохранить подключение" : "Подключить репозиторий"}
      </Button>
    </div>
  );
};

const Connected = ({ project, onAudited }: Props) => {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const commits = useQuery({ queryKey: ["gh", project.id, "commits", project.gh_branch], queryFn: () => studioApi.ghCommits(project.id), retry: false });
  const files = useQuery({ queryKey: ["gh", project.id, "files", project.gh_branch], queryFn: () => studioApi.ghFiles(project.id), retry: false });

  const audit = useMutation({
    mutationFn: () => studioApi.ghAudit(project.id),
    onSuccess: (r) => {
      toast.success("Аудит по репозиторию выполнен");
      qc.invalidateQueries({ queryKey: ["project", project.id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      onAudited(r.audit_id);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const disconnect = useMutation({
    mutationFn: () => studioApi.ghDisconnect(project.id),
    onSuccess: () => {
      toast.success("Репозиторий отключён, токен удалён");
      qc.invalidateQueries({ queryKey: ["project", project.id] });
    },
  });

  const list = (files.data?.files ?? []).filter(([p]) => !q || p.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-5">
      <div className="glass-card flex flex-wrap items-center justify-between gap-4 rounded-2xl p-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-semibold">
            <Icon name="Github" size={18} /> {project.gh_repo}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            Ветка: {project.gh_branch} · {project.gh_has_token ? "токен сохранён" : "без токена (публичный доступ)"} · только чтение
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => audit.mutate()} disabled={audit.isPending}>
            <Icon name="FileSearch" size={15} className="mr-1.5" />
            {audit.isPending ? "Скачиваю и анализирую…" : "Повторить аудит"}
          </Button>
          <Button variant="secondary" onClick={() => disconnect.mutate()} disabled={disconnect.isPending}>
            Отключить
          </Button>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Аудит строится по снимку ветки с GitHub. Код не запускается, зависимости не устанавливаются, в репозиторий ничего не записывается. Сборка и запуск: не проверено.
      </p>

      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold">Последние коммиты</h3>
          <div className="glass-card divide-y divide-border rounded-xl">
            {commits.isLoading && <p className="p-4 text-sm text-muted-foreground">Загрузка…</p>}
            {commits.error && <p className="p-4 text-sm text-destructive">{(commits.error as Error).message}</p>}
            {commits.data?.commits.map((c) => (
              <div key={c.sha} className="p-3 text-sm">
                <div className="line-clamp-2">{c.message}</div>
                <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                  <code>{c.sha.slice(0, 7)}</code>
                  <span>{c.author}</span>
                  {c.date && <span>{fmtDate(c.date)}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-semibold">
            Файлы{files.data ? ` (${files.data.total})` : ""}
          </h3>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по файлам" className="mb-2" />
          <div className="max-h-[420px] overflow-auto rounded-lg border border-border bg-background/60 p-2 font-mono text-xs">
            {files.isLoading && <p className="p-3 text-muted-foreground">Загрузка…</p>}
            {files.error && <p className="p-3 text-destructive">{(files.error as Error).message}</p>}
            {list.slice(0, 1500).map(([p, size]) => (
              <div key={p} className="flex justify-between gap-4 rounded px-2 py-1 hover:bg-secondary">
                <span className="truncate">{p}</span>
                <span className="shrink-0 text-muted-foreground">{fmtBytes(size)}</span>
              </div>
            ))}
            {files.data && list.length === 0 && <p className="p-3 text-muted-foreground">Ничего не найдено</p>}
          </div>
          {files.data?.truncated && (
            <p className="mt-2 text-xs text-amber-300">Список неполный: показаны первые {files.data.files.length} из {files.data.total}.</p>
          )}
        </div>
      </div>

      <details className="rounded-xl border border-border p-4">
        <summary className="cursor-pointer text-sm">Изменить подключение</summary>
        <div className="mt-4"><ConnectForm project={project} /></div>
      </details>
    </div>
  );
};

export const RepoTab = ({ project, onAudited }: Props) =>
  project.gh_repo ? <Connected project={project} onAudited={onAudited} /> : <ConnectForm project={project} />;
