import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import Icon from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fileToBase64, fmtBytes, studioApi, TEMPLATE_LABELS } from "@/lib/studio-api";

const MAX_BYTES = 8 * 1024 * 1024;

type Props = { open: boolean; onOpenChange: (v: boolean) => void; initialTab?: "create" | "import" };

export const NewProjectDialog = ({ open, onOpenChange, initialTab = "import" }: Props) => {
  const nav = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [template, setTemplate] = useState("empty");
  const [file, setFile] = useState<File | null>(null);
  const [repo, setRepo] = useState("");

  const pickFile = (f: File | null) => {
    if (f && f.size > MAX_BYTES) {
      toast.error(`Архив ${fmtBytes(f.size)} — лимит 8 МБ. Удалите node_modules и dist из архива.`);
      return;
    }
    setFile(f);
  };

  const create = async () => {
    if (!name.trim()) return toast.error("Укажите название проекта");
    setBusy(true);
    try {
      const { id } = await studioApi.create({ name, description: desc, template });
      onOpenChange(false);
      nav(`/projects/${id}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const doImport = async () => {
    if (!file) return toast.error("Выберите ZIP-архив");
    setBusy(true);
    try {
      const file_base64 = await fileToBase64(file);
      const { id } = await studioApi.import({
        name,
        description: desc,
        repo_url: repo,
        filename: file.name,
        file_base64,
      });
      onOpenChange(false);
      nav(`/projects/${id}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-heading">Новый проект</DialogTitle>
          <DialogDescription>Создайте запись или загрузите ZIP для аудита</DialogDescription>
        </DialogHeader>
        <Tabs defaultValue={initialTab}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="import">Импорт ZIP</TabsTrigger>
            <TabsTrigger value="create">Создать</TabsTrigger>
          </TabsList>

          <TabsContent value="import" className="mt-4 space-y-4">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex w-full flex-col items-center gap-2 rounded-xl border border-dashed border-border p-6 text-sm transition-colors hover:border-primary/60"
            >
              <Icon name={file ? "FileArchive" : "Upload"} size={24} className="text-primary" />
              {file ? (
                <span className="font-medium">
                  {file.name} <span className="text-muted-foreground">· {fmtBytes(file.size)}</span>
                </span>
              ) : (
                <span className="text-muted-foreground">Выберите ZIP до 8 МБ (без node_modules)</span>
              )}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".zip,application/zip"
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0] || null)}
            />
            <div className="space-y-1.5">
              <Label>Название (необязательно)</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Возьмём из package.json" />
            </div>
            <div className="space-y-1.5">
              <Label>Адрес репозитория (необязательно)</Label>
              <Input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="https://github.com/..." />
            </div>
            <p className="text-xs text-muted-foreground">
              Архив разбирается статически: код не запускается, зависимости не устанавливаются. Сам архив не сохраняется — только отчёт и список файлов.
            </p>
            <Button className="w-full" onClick={doImport} disabled={busy || !file}>
              {busy ? "Анализирую…" : "Загрузить и проанализировать"}
            </Button>
          </TabsContent>

          <TabsContent value="create" className="mt-4 space-y-4">
            <div className="space-y-1.5">
              <Label>Название</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Сайт юридической компании" />
            </div>
            <div className="space-y-1.5">
              <Label>Описание</Label>
              <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3} />
            </div>
            <div className="space-y-1.5">
              <Label>Шаблон</Label>
              <div className="grid gap-2">
                {Object.entries(TEMPLATE_LABELS).map(([k, v]) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setTemplate(k)}
                    className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                      template === k ? "border-primary bg-primary/10" : "border-border hover:border-primary/40"
                    }`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Генерация сайта не подключена: сохраняются только название, описание и выбранный шаблон.
            </p>
            <Button className="w-full" onClick={create} disabled={busy}>
              {busy ? "Сохраняю…" : "Создать запись проекта"}
            </Button>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};
