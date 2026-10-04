import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "@/components/ui/icon";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { auth, studioApi } from "@/lib/studio-api";

type State = "checking" | "locked" | "open";

export const AuthGate = ({ children }: { children: ReactNode }) => {
  const [state, setState] = useState<State>(auth.get() ? "checking" : "locked");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onLogout = () => setState("locked");
    window.addEventListener("studio-logout", onLogout);
    return () => window.removeEventListener("studio-logout", onLogout);
  }, []);

  useEffect(() => {
    if (state !== "checking") return;
    studioApi
      .check()
      .then(() => setState("open"))
      .catch(() => {
        auth.clear();
        setState("locked");
      });
  }, [state]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { token } = await studioApi.login(password);
      auth.set(token);
      setPassword("");
      setState("open");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (state === "open") return <>{children}</>;
  if (state === "checking") return <div className="p-8 text-sm text-muted-foreground">Проверка доступа…</div>;

  return (
    <div className="flex min-h-screen items-center justify-center px-5">
      <form onSubmit={submit} className="glass-card w-full max-w-sm space-y-4 rounded-2xl p-7">
        <div className="flex items-center gap-2">
          <Icon name="Lock" size={18} className="text-primary" />
          <h1 className="font-heading text-lg font-bold">AI Web Studio</h1>
        </div>
        <p className="text-sm text-muted-foreground">Закрытый кабинет. Введите пароль администратора.</p>
        <Input
          type="password"
          autoFocus
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Пароль"
        />
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={busy || !password}>
          {busy ? "Проверяю…" : "Войти"}
        </Button>
        <Link to="/" className="block text-center text-xs text-muted-foreground hover:text-foreground">
          На сайт
        </Link>
      </form>
    </div>
  );
};
