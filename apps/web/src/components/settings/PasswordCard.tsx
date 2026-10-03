"use client";

import { useState } from "react";
import { Button, TextField, useAction } from "@/components/forms";
import { Card } from "@/components/ui";
import { apiSend } from "@/lib/api";
import { setToken } from "@/lib/auth";

export function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const act = useAction();
  return (
    <Card title="Admin password">
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label="Current password" type="password" value={current} onChange={setCurrent} autoComplete="current-password" />
        <TextField label="New password" type="password" value={next} onChange={setNext} autoComplete="new-password" hint="At least 10 characters. Signs out other sessions." />
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Button
          onClick={async () => {
            const ok = await act.run(async () => {
              const r = await apiSend<{ token: string }>("/api/v1/auth/change-password", "POST", { current_password: current, new_password: next });
              setToken(r.token);
            }, "Password changed.");
            if (ok) {
              setCurrent("");
              setNext("");
            }
          }}
        >
          Change password
        </Button>
        {act.view}
      </div>
    </Card>
  );
}
