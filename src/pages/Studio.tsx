import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Icon from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { NewProjectDialog } from "@/components/studio/NewProjectDialog";
import { fmtDate, ProjectRow, STATUS_META, studioApi } from "@/lib/studio-api";

const Card = ({ p }: { p: ProjectRow }) => (
  <Link
    to={`/projects/${p.id}`}
    className="glass-card glow-hover block rounded-2xl p-5"
  >
    <div className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="truncate font-heading text-lg font-bold">{p.name}</h3>
        <p className="mt-0.5 line-clamp-2 min-h-[2.5rem] text-sm text-muted-foreground">
          {p.description || p.stack || "Без описания"}
        </p>
      </div>
      <span className="shrink-0 rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground">
        {p.source_type === "zip" ? "Импорт ZIP" : "Новый"}
      </span>
    </div>

    {p.counts ? (
      <div className="mb-3 flex flex-wrap gap-1.5">
        {(Object.keys(STATUS_META) as (keyof typeof STATUS_META)[]).map((k) => (
          <span key={k} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${STATUS_META[k].cls}`} title={STATUS_META[k].label}>
            <Icon name={STATUS_META[k].icon} size={11} />
            {p.counts![k]}
          </span>
        ))}
      </div>
    ) : (
      <p className="mb-3 text-xs text-muted-foreground">Аудит не проводился</p>
    )}

    <div className="space-y-1 border-t border-border pt-3 text-xs text-muted-foreground">
      <div className="flex items-center gap-1.5">
        <Icon name="Play" size={12} /> Запуск: не подключён
      </div>
      <div className="flex items-center gap-1.5">
        <Icon name="GitBranch" size={12} />
        <span className="truncate">{p.repo_url || "Репозиторий не указан"}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Icon name="Clock" size={12} /> {fmtDate(p.updated_at)}
      </div>
    </div>
  </Link>
);

const Studio = () => {
  const [archived, setArchived] = useState(false);
  const [dialog, setDialog] = useState<"create" | "import" | null>(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["projects", archived],
    queryFn: () => studioApi.list(archived),
  });

  return (
    <div className="min-h-screen">
      <div className="mesh-bg">
        <div className="mesh-orb" />
        <div className="mesh-orb" />
        <div className="mesh-orb" />
        <div className="mesh-orb" />
      </div>
      <div className="relative z-10 mx-auto max-w-6xl px-5 py-8">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <Link to="/" className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
              <Icon name="ArrowLeft" size={12} /> На сайт
            </Link>
            <h1 className="font-heading text-3xl font-black">
              <span className="gradient-text">AI Web Studio</span>
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">Проекты, импорт и аудит переносимости</p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setDialog("create")}>
              <Icon name="Plus" size={16} className="mr-1.5" /> Создать проект
            </Button>
            <Button onClick={() => setDialog("import")}>
              <Icon name="Upload" size={16} className="mr-1.5" /> Импортировать ZIP
            </Button>
          </div>
        </header>

        <div className="mb-5 flex items-center gap-2">
          <Switch id="arch" checked={archived} onCheckedChange={setArchived} />
          <Label htmlFor="arch" className="text-sm text-muted-foreground">Показать архив</Label>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
        {error && <p className="text-sm text-destructive">{(error as Error).message}</p>}

        {data && data.length === 0 && (
          <div className="glass-card flex flex-col items-center gap-3 rounded-2xl p-12 text-center">
            <Icon name="FolderOpen" size={32} className="text-muted-foreground" />
            <h3 className="font-heading text-lg font-bold">Проектов пока нет</h3>
            <p className="max-w-md text-sm text-muted-foreground">
              Загрузите ZIP проекта, экспортированного из Poehali или другого источника, чтобы получить отчёт о переносимости.
            </p>
            <Button onClick={() => setDialog("import")}>Импортировать ZIP</Button>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data?.map((p) => <Card key={p.id} p={p} />)}
        </div>
      </div>

      <NewProjectDialog
        key={dialog ?? "closed"}
        open={dialog !== null}
        onOpenChange={(v) => !v && setDialog(null)}
        initialTab={dialog ?? "import"}
      />
    </div>
  );
};

export default Studio;
