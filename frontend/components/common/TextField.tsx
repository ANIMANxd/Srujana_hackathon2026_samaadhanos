"use client";

import { useId, useState } from "react";
import type { MessageKey } from "@/lib/i18n/en";
import { useT } from "@/lib/i18n";

export const DATE = /^\d{4}-\d{2}-\d{2}$/;
export const AMOUNT = /^\d+(\.\d{1,2})?$/;
export const INT = /^\d+$/;
export const DECIMAL = /^\d+(\.\d{1,4})?$/;

/** A syntactically valid YYYY-MM-DD that also exists in the calendar (no 31 Feb). */
export function isRealDate(value: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return false;
  const [y, mo, d] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const dt = new Date(Date.UTC(y, mo - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d;
}

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
  const errorId = useId();
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  if (synced !== value) {
    setSynced(value);
    setDraft(value);
  }
  const empty = draft === "";
  const formatOk = pattern === DATE ? DATE.test(draft) : pattern.test(draft);
  const realDate = pattern === DATE && formatOk ? isRealDate(draft) : true;
  const valid = (allowEmpty && empty) || (formatOk && realDate);
  const shownError: MessageKey = empty && !allowEmpty ? "common.required" : formatOk && !realDate ? "judge.invalid_date_real" : errorKey;
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <input
        className={`field-input ${mono ? "num" : ""}`}
        value={draft}
        aria-invalid={!valid}
        aria-required={!allowEmpty}
        aria-describedby={!valid ? errorId : undefined}
        onChange={(e) => {
          const v = e.target.value.trim();
          setDraft(v);
          if ((allowEmpty && v === "") || (pattern === DATE ? DATE.test(v) && isRealDate(v) : pattern.test(v))) onCommit(v);
        }}
      />
      {!valid && (
        <span id={errorId} role="alert" className="mt-1 block text-xs text-block">
          {t(shownError)}
        </span>
      )}
    </label>
  );
}
