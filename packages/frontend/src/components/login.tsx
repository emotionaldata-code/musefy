import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { Brand } from "@/components/brand";
import { apiBaseURL } from "@/lib/api";

function loginURL(): string {
  const location = new URL(window.location.href);
  location.searchParams.delete("auth_error");
  const returnTo = `${location.pathname}${location.search}${location.hash}`;
  return `${apiBaseURL}/auth/google?${new URLSearchParams({ return_to: returnTo })}`;
}

export function Login({
  status,
  retry,
}: {
  status: "checking" | "anonymous" | "error";
  retry: () => void;
}) {
  const authError = new URLSearchParams(window.location.search).has(
    "auth_error",
  );
  return (
    <main className="login-page">
      <div className="login-theme">
        <ThemeToggle />
      </div>
      <section className="login-content" aria-labelledby="login-heading">
        <div className="brand login-brand" aria-label="Musefy">
          <Brand />
        </div>
        <h1 id="login-heading">Accedi a Musefy</h1>
        <p>
          Film, serie TV, anime e manga. La tua prossima scoperta parte da qui.
        </p>
        {status === "checking" ? (
          <div className="login-status" role="status">
            Verifica dell’accesso…
          </div>
        ) : status === "error" ? (
          <div className="login-feedback">
            <p role="alert">
              Non riusciamo a verificare l’accesso. Riprova tra poco.
            </p>
            <Button
              variant="secondary"
              className="login-button"
              onClick={retry}
            >
              Riprova
            </Button>
          </div>
        ) : (
          <>
            {authError && (
              <p className="login-error" role="alert">
                Accesso non completato. Puoi riprovare con Google.
              </p>
            )}
            <Button asChild variant="outline" className="login-button">
              <a href={loginURL()}>
                <svg
                  viewBox="0 0 48 48"
                  aria-hidden="true"
                  className="google-mark"
                >
                  <path
                    fill="#EA4335"
                    d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z"
                  />
                  <path
                    fill="#4285F4"
                    d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6C44.4 38.03 46.98 31.87 46.98 24.55Z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M10.53 28.59A14.41 14.41 0 0 1 9.75 24c0-1.59.27-3.13.76-4.59l-7.98-6.19A23.87 23.87 0 0 0 0 24c0 3.87.93 7.52 2.56 10.78l7.97-6.19Z"
                  />
                  <path
                    fill="#34A853"
                    d="M24 48c6.48 0 11.93-2.13 15.91-5.8l-7.73-6c-2.15 1.45-4.92 2.3-8.18 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48Z"
                  />
                </svg>
                Continua con Google
              </a>
            </Button>
            <p className="login-note">
              Al primo accesso creiamo il tuo account con nome, email e immagine
              del profilo Google.
            </p>
          </>
        )}
      </section>
    </main>
  );
}
