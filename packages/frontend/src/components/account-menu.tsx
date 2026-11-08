import { useState } from "react";
import { DropdownMenu } from "radix-ui";
import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Account } from "@/lib/use-auth";

export function AccountMenu({
  user,
  logout,
  loggingOut,
  logoutError,
}: {
  user: Account;
  logout: () => Promise<void>;
  loggingOut: boolean;
  logoutError: boolean;
}) {
  const [pictureFailed, setPictureFailed] = useState(false);
  const initial = (user.name?.trim() || user.email)
    .slice(0, 1)
    .toLocaleUpperCase();
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <Button
          variant="ghost"
          className="account-trigger"
          aria-label={`Account: ${user.email}`}
        >
          <span className="account-avatar" aria-hidden="true">
            {user.picture && !pictureFailed ? (
              <img
                src={user.picture}
                alt=""
                referrerPolicy="no-referrer"
                onError={() => setPictureFailed(true)}
              />
            ) : (
              initial
            )}
          </span>
          <span className="account-email">{user.email}</span>
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          collisionPadding={16}
          className="account-menu"
        >
          <DropdownMenu.Label className="account-label">
            {user.name && <span>{user.name}</span>}
            <span className="account-menu-email">{user.email}</span>
          </DropdownMenu.Label>
          <DropdownMenu.Item
            className="account-menu-item"
            disabled={loggingOut}
            onSelect={(event) => {
              event.preventDefault();
              void logout();
            }}
          >
            <LogOut size={16} aria-hidden="true" />
            {loggingOut ? "Uscita in corso…" : "Esci"}
          </DropdownMenu.Item>
          {logoutError && (
            <p className="account-error" role="alert">
              Uscita non riuscita. Riprova.
            </p>
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
