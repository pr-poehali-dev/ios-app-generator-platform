import Icon from "@/components/ui/icon";
import { AuditStatus, STATUS_META } from "@/lib/studio-api";

export const StatusBadge = ({ status }: { status: AuditStatus }) => {
  const m = STATUS_META[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${m.cls}`}>
      <Icon name={m.icon} size={12} />
      {m.label}
    </span>
  );
};

export const NotConnected = ({ icon, title, text }: { icon: string; title: string; text: string }) => (
  <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border p-10 text-center">
    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary text-muted-foreground">
      <Icon name={icon} size={22} />
    </div>
    <div className="flex items-center gap-2">
      <h3 className="font-heading text-base font-bold">{title}</h3>
      <span className="rounded-full border border-slate-500/30 bg-slate-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-300">
        не подключено
      </span>
    </div>
    <p className="max-w-md text-sm text-muted-foreground">{text}</p>
  </div>
);
