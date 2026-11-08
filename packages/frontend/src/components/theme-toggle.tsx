import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "./ui/button";

export function ThemeToggle() {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    function followSystem(): void {
      try {
        if (localStorage.getItem("musefy-theme")) return;
      } catch {
        /* Storage may be disabled. */
      }
      document.documentElement.classList.toggle("dark", media.matches);
      setDark(media.matches);
    }
    followSystem();
    media.addEventListener("change", followSystem);
    return () => media.removeEventListener("change", followSystem);
  }, []);

  function toggle(): void {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    setDark(next);
    try {
      localStorage.setItem("musefy-theme", next ? "dark" : "light");
    } catch {
      /* The toggle still works without storage. */
    }
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label={dark ? "Attiva tema chiaro" : "Attiva tema scuro"}
      title={dark ? "Tema chiaro" : "Tema scuro"}
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </Button>
  );
}
