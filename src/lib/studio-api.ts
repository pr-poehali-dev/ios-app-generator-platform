import func2url from "../../backend/func2url.json";

const URL_STUDIO = (func2url as Record<string, string>).studio;

export type Counts = {
  portable: number;
  needs_setup: number;
  needs_adaptation: number;
  unknown: number;
};

export type ProjectRow = {
  id: number;
  name: string;
  description: string;
  template: string;
  source_type: "new" | "zip";
  repo_url: string;
  stack: string;
  archived: boolean;
  created_at: string;
  updated_at: string;
  last_audit_id: number | null;
  last_audit_at: string | null;
  counts: Counts | null;
  poehali_detected: boolean | null;
};

export type AuditSummary = {
  id: number;
  filename: string;
  archive_size: number;
  created_at: string;
  counts: Counts;
};

export type ProjectFull = Omit<ProjectRow, "last_audit_id" | "last_audit_at" | "counts" | "poehali_detected"> & {
  install_cmd: string;
  dev_cmd: string;
  build_cmd: string;
  output_dir: string;
  node_version: string;
  audits: AuditSummary[];
};

export type AuditStatus = keyof Counts;

export type AuditItem = {
  category: string;
  status: AuditStatus;
  title: string;
  detail: string;
  evidence: string[];
};

export type Detected = { value: string; source: string; confidence: "found" | "inferred" | "none"; script?: string };

export type AuditReport = {
  notice: string;
  archive: { filename: string; compressed: number; files: number; uncompressed: number; root_folder: string };
  poehali_detected: boolean;
  stack: string[];
  package: {
    name: string;
    version: string;
    scripts: Record<string, string>;
    prod: Record<string, string>;
    dev: Record<string, string>;
  };
  commands: {
    package_manager: string;
    install: Detected;
    dev: Detected;
    build: Detected;
    output_dir: Detected;
    node_version: Detected;
  };
  lockfiles: string[];
  configs: string[];
  functions: {
    name: string;
    path: string;
    language: string;
    has_handler: boolean;
    has_tests: boolean;
    requirements: string[];
    uses_db: boolean;
    uses_storage: boolean;
  }[];
  func2url: string[];
  migrations: string[];
  python: { files: Record<string, string[]>; root: string[] };
  env_vars: { name: string; files: string[]; likely_platform: boolean; client_side: boolean }[];
  env_files: string[];
  poehali_refs: { host: string; count: number; files: string[] }[];
  extensions: [string, number][];
  skipped_dirs: Record<string, number>;
  warnings: string[];
  items: AuditItem[];
  counts: Counts;
};

export type AuditFull = {
  id: number;
  project_id: number;
  filename: string;
  archive_size: number;
  created_at: string;
  report: AuditReport;
  tree: [string, number][];
};

async function call<T>(init?: RequestInit, query = ""): Promise<T> {
  const res = await fetch(URL_STUDIO + query, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Ошибка сервера");
  return data as T;
}

const post = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const studioApi = {
  list: (archived = false) =>
    call<{ projects: ProjectRow[] }>(undefined, archived ? "?archived=1" : "").then((r) => r.projects),
  get: (id: number) => call<ProjectFull>(undefined, `?id=${id}`),
  audit: (id: number) => call<AuditFull>(undefined, `?audit_id=${id}`),
  create: (v: { name: string; description: string; template: string }) =>
    call<{ id: number }>(post({ action: "create", ...v })),
  import: (v: { name: string; description: string; repo_url: string; filename: string; file_base64: string }) =>
    call<{ id: number; audit_id: number }>(post({ action: "import", ...v })),
  update: (id: number, patch: Partial<ProjectFull>) => call<{ ok: boolean }>(post({ id, ...patch }, "PUT")),
};

export const fileToBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] || "");
    r.onerror = () => reject(new Error("Не удалось прочитать файл"));
    r.readAsDataURL(file);
  });

export const fmtBytes = (n: number) =>
  n < 1024 ? `${n} Б` : n < 1048576 ? `${(n / 1024).toFixed(1)} КБ` : `${(n / 1048576).toFixed(1)} МБ`;

export const fmtDate = (s: string) =>
  new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

export const STATUS_META: Record<AuditStatus, { label: string; cls: string; icon: string }> = {
  portable: { label: "Переносимо", cls: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30", icon: "CircleCheck" },
  needs_setup: { label: "Требует настройки", cls: "text-amber-300 bg-amber-500/10 border-amber-500/30", icon: "Settings2" },
  needs_adaptation: { label: "Требует адаптации", cls: "text-orange-300 bg-orange-500/10 border-orange-500/30", icon: "Wrench" },
  unknown: { label: "Не удалось определить", cls: "text-slate-300 bg-slate-500/10 border-slate-500/30", icon: "CircleHelp" },
};

export const TEMPLATE_LABELS: Record<string, string> = {
  empty: "Пустой React-проект",
  vite: "React + TypeScript + Vite",
  tailwind: "React + TypeScript + Tailwind",
  components: "React + TypeScript + библиотека компонентов",
};
