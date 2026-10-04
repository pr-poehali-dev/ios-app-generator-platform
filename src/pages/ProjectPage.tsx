import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import Icon from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AuditReportView } from "@/components/studio/AuditReportView";
import { NotConnected } from "@/components/studio/StatusBadge";
import { fmtBytes, fmtDate, ProjectFull, projectKind, studioApi, TEMPLATE_LABELS } from "@/lib/studio-api";

const FIELDS: [keyof ProjectFull, string, string][] = [
  ["repo_url", "Репозиторий", "https://github.com/..."],
  ["stack", "Стек", "React, Vite, TypeScript"],
  ["install_cmd", "Команда установки", "npm ci"],
  ["dev_cmd", "Команда запуска", "npm run dev"],
  ["build_cmd", "Команда сборки", "npm run build"],
  ["output_dir", "Папка результата", "dist"],
  ["node_version", "Версия Node.js", "20"],
];

const Settings = ({ project }: { project: ProjectFull }) => {
  const qc = useQueryClient();
  const [form, setForm] = useState(project);
  useEffect(() => setForm(project), [project]);

  const save = useMutation({
    mutationFn: () =>
      studioApi.update(project.id, {
        name: form.name, description: form.description, repo_url: form.repo_url, stack: form.stack,
        install_cmd: form.install_cmd, dev_cmd: form.dev_cmd, build_cmd: form.build_cmd,
        output_dir: form.output_dir, node_version: form.node_version,
      }),
    onSuccess: () => {
      toast.success("Настройки сохранены");
      qc.invalidateQueries({ queryKey: ["project", project.id] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const set = (k: keyof ProjectFull, v: string) => setForm({ ...form, [k]: v });

  return (
    <div className="glass-card max-w-2xl space-y-4 rounded-2xl p-6">
      <div className="space-y-1.5">
        <Label>Название</Label>
        <Input value={form.name} onChange={(e) => set("name", e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label>Описание</Label>
        <Textarea rows={3} value={form.description} onChange={(e) => set("description", e.target.value)} />
      </div>
      {FIELDS.map(([k, label, ph]) => (
        <div key={k} className="space-y-1.5">
          <Label>{label}</Label>
          <Input value={String(form[k] ?? "")} placeholder={ph} onChange={(e) => set(k, e.target.value)} />
        </div>
      ))}
      <p className="text-xs text-muted-foreground">
        Команды заполнены автоматически по файлам архива и могут быть неточными. Они не запускались — статус: не проверено.
      </p>
      <Button onClick={() => save.mutate()} disabled={save.isPending}>Сохранить</Button>
    </div>
  );
};

const ProjectPage = () => {
  const { id } = useParams();
  const pid = Number(id);
  const qc = useQueryClient();
  const [auditId, setAuditId] = useState<number | null>(null);

  const { data: project, isLoading, error } = useQuery({
    queryKey: ["project", pid],
    queryFn: () => studioApi.get(pid),
  });

  const currentAuditId = auditId ?? project?.audits[0]?.id ?? null;
  const { data: audit, isLoading: auditLoading } = useQuery({
    queryKey: ["audit", currentAuditId],
    queryFn: () => studioApi.audit(currentAuditId as number),
    enabled: currentAuditId !== null,
  });

  const archive = useMutation({
    mutationFn: (v: boolean) => studioApi.update(pid, { archived: v }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", pid] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Готово");
    },
  });

  if (isLoading) return <div className="p-8 text-sm text-muted-foreground">Загрузка…</div>;
  if (error || !project) return <div className="p-8 text-sm text-destructive">{(error as Error)?.message || "Проект не найден"}</div>;

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-6xl px-5 py-8">
        <Link to="/studio" className="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <Icon name="ArrowLeft" size={12} /> Все проекты
        </Link>
        <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-heading text-2xl font-black">{project.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {projectKind(project).label} · {projectKind(project).hint}
              {project.source_type === "new" ? ` · шаблон: ${TEMPLATE_LABELS[project.template] || project.template}` : ""} · обновлён {fmtDate(project.updated_at)}
            </p>
            {project.description && <p className="mt-2 max-w-2xl text-sm">{project.description}</p>}
          </div>
          <Button variant="secondary" size="sm" onClick={() => archive.mutate(!project.archived)}>
            <Icon name="Archive" size={14} className="mr-1.5" />
            {project.archived ? "Вернуть из архива" : "В архив"}
          </Button>
        </header>

        <Tabs defaultValue={project.source_type === "zip" ? "audit" : "settings"}>
          <TabsList className="flex h-auto flex-wrap justify-start">
            <TabsTrigger value="audit">Аудит</TabsTrigger>
            <TabsTrigger value="assistant">AI-чат</TabsTrigger>
            <TabsTrigger value="files">Файлы</TabsTrigger>
            <TabsTrigger value="changes">Изменения</TabsTrigger>
            <TabsTrigger value="preview">Предпросмотр</TabsTrigger>
            <TabsTrigger value="history">История</TabsTrigger>
            <TabsTrigger value="settings">Настройки</TabsTrigger>
          </TabsList>

          <TabsContent value="audit" className="mt-5">
            {project.audits.length === 0 && (
              <NotConnected icon="FileSearch" title="Аудит не проводился" text="Это черновик задания. Аудит появляется только у проектов, импортированных из ZIP." />
            )}
            {project.audits.length > 0 && (
              <>
                <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Архив:</span>
                  {project.audits.map((a) => (
                    <button
                      key={a.id}
                      onClick={() => setAuditId(a.id)}
                      className={`rounded-lg border px-3 py-1.5 text-xs ${currentAuditId === a.id ? "border-primary bg-primary/10" : "border-border"}`}
                    >
                      {a.filename} · {fmtBytes(a.archive_size)} · {fmtDate(a.created_at)}
                    </button>
                  ))}
                </div>
                {auditLoading && <p className="text-sm text-muted-foreground">Загрузка отчёта…</p>}
                {audit && <AuditReportView audit={audit} />}
              </>
            )}
          </TabsContent>

          <TabsContent value="assistant" className="mt-5">
            <NotConnected icon="MessageSquare" title="AI-чат" text="AI-агент для правки кода не подключён. Для него нужен отдельный runner на вашем компьютере или сервере." />
          </TabsContent>
          <TabsContent value="files" className="mt-5">
            <NotConnected icon="Files" title="Редактор файлов" text="Рабочая копия проекта не подключена, исходники не хранятся. Сейчас сохраняется только список файлов из аудита." />
          </TabsContent>
          <TabsContent value="changes" className="mt-5">
            <NotConnected icon="GitCompare" title="Изменения и diff" text="Появятся вместе с AI-агентом и Git. Сейчас никакие изменения не создаются." />
          </TabsContent>
          <TabsContent value="preview" className="mt-5">
            <NotConnected icon="MonitorPlay" title="Предпросмотр" text="Сборка и запуск: не проверено. Исполнять чужой код внутри этой платформы нельзя — нужен отдельный runner." />
          </TabsContent>
          <TabsContent value="history" className="mt-5">
            <NotConnected icon="History" title="История версий" text="Git-коммитов нет. Здесь появятся версии после подключения репозитория и runner." />
          </TabsContent>
          <TabsContent value="settings" className="mt-5">
            <Settings project={project} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default ProjectPage;
