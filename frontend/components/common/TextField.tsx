"use client";

import { useState } from "react";
import type { MessageKey } from "@/lib/i18n/en";
import { useT } from "@/lib/i18n";

export const DATE = /^\d{4}-\d{2}-\d{2}$/;
export const AMOUNT = /^\d+(\.\d{1,2})?$/;
export const INT = /^\d+$/;
export const DECIMAL = /^\d+(\.\d{1,4})?$/;

/**
 * Text input that keeps its own draft and only commits valid values, with a
 * plain-language message while the draft is invalid. Used wherever a person
 * edits a case input (judge console, evidence locker).
 */
export function TextField({
  label,
  value,
  pattern,
  errorKey,
  allowEmpty,
  onCommit,
  mono = true,
}: {
  label: string;
  value: string;
  pattern: RegExp;
  errorKey: MessageKey;
  allowEmpty: boolean;
  onCommit: (v: string) => void;
  mono?: boolean;
}) {
  const { t } = useT();
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  if (synced !== value) {
    setSynced(value);
    setDraft(value);
  }
  const valid = (allowEmpty && draft === "") || pattern.test(draft);
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <input
        className={`field-input ${mono ? "num" : ""}`}
        value={draft}
        aria-invalid={!valid}
        onChange={(e) => {
          const v = e.target.value.trim();
          setDraft(v);
          if ((allowEmpty && v === "") || pattern.test(v)) onCommit(v);
        }}
      />
      {!valid && <span className="mt-1 block text-xs text-block">{t(errorKey)}</span>}
    </label>
  );
}
