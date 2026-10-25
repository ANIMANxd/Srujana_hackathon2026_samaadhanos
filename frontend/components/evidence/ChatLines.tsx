"use client";

import { useRef, useState } from "react";
import { ApiError, BackendUnreachable, extractEvidence } from "@/lib/api";
import { EXTRACTION_SAMPLES } from "@/lib/fixtures";
import { useT } from "@/lib/i18n";
import type { ExtractedMessage, MessageTag } from "@/lib/types";
import { Icon } from "../common/Icon";
import { Banner } from "../shell/Banners";

const DELIVERY: MessageTag[] = ["DELIVERY_CONFIRMATION"];
const OBJECTION: MessageTag[] = ["DEFECT_OBJECTION", "LATE_COMPLAINT"];

type Result = { messages: ExtractedMessage[]; offlineSample: boolean };

/**
 * Line-citation viewer for a pasted WhatsApp export. The backend extractor
 * tags each message with its 1-based line; this view only highlights those
 * lines. Tags are machine suggestions and change nothing in the case.
 */
export function ChatLines() {
  const { t, tCode } = useT();
  const file = useRef<HTMLInputElement>(null);
  const sample = EXTRACTION_SAMPLES.find((s) => s.response.kind === "WHATSAPP_EXPORT") ?? null;
  const [text, setText] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);

  async function read(body: string) {
    setError(null);
    setReading(true);
    try {
      const res = await extractEvidence(new Blob([body], { type: "text/plain" }), "chat.txt");
      setResult({ messages: res.messages ?? [], offlineSample: false });
    } catch (e) {
      if (e instanceof BackendUnreachable) {
        if (sample && body === sample.text) setResult({ messages: sample.response.messages ?? [], offlineSample: true });
        else {
          setResult(null);
          setError(t("locker.chat.offline"));
        }
      } else {
        setResult(null);
        setError(e instanceof ApiError ? e.message : t("state.error_title"));
      }
    } finally {
      setReading(false);
    }
  }

  const byLine = new Map<number, ExtractedMessage>();
  (result?.messages ?? []).forEach((m) => byLine.set(m.line, m));
  const lines = text.split(/\r?\n/);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h3 className="text-sm font-medium text-ink-950">{t("locker.chat.title")}</h3>
        <p className="text-xs text-ink-500">{t("locker.chat.intro")}</p>
      </div>

      <label className="flex flex-col">
        <span className="sr-only">{t("locker.chat.paste")}</span>
        <textarea
          className="field-input min-h-28 font-mono text-xs leading-relaxed"
          placeholder={t("locker.chat.paste")}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setResult(null);
          }}
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary min-h-9" disabled={reading || text.trim() === ""} onClick={() => void read(text)}>
          {t("locker.chat.read")}
        </button>
        <button type="button" className="btn btn-secondary min-h-9" onClick={() => file.current?.click()}>
          <Icon name="upload" className="h-4 w-4" />
          {t("locker.chat.choose")}
        </button>
        {sample && (
          <button
            type="button"
            className="btn btn-quiet min-h-9"
            onClick={() => {
              setText(sample.text);
              void read(sample.text);
            }}
          >
            {t("locker.chat.sample")}
          </button>
        )}
        {text && (
          <button
            type="button"
            className="btn btn-quiet min-h-9"
            onClick={() => {
              setText("");
              setResult(null);
              setError(null);
            }}
          >
            {t("locker.chat.clear")}
          </button>
        )}
        <input
          ref={file}
          type="file"
          accept=".txt,text/plain"
          className="sr-only"
          tabIndex={-1}
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const body = await f.text();
            setText(body);
            void read(body);
          }}
        />
      </div>

      {error && <p role="alert" className="text-sm text-block">{error}</p>}
      {result?.offlineSample && <Banner tone="info" icon="info" message="locker.chat.offline_sample" />}

      {result && (
        <>
          <div className="flex flex-wrap items-center gap-4 text-xs text-ink-600">
            <span className="flex items-center gap-1.5">
              <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-ok-wash ring-1 ring-ok/40" />
              {t("locker.chat.legend_delivery")}
            </span>
            <span className="flex items-center gap-1.5">
              <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-warn-wash ring-1 ring-warn/40" />
              {t("locker.chat.legend_objection")}
            </span>
          </div>
          <ol className="max-h-80 overflow-auto rounded-lg border border-rule font-mono text-xs leading-relaxed">
            {lines.map((line, i) => {
              const n = i + 1;
              const m = byLine.get(n);
              const tags = m?.tags ?? [];
              const tone = tags.some((x) => OBJECTION.includes(x)) ? "objection" : tags.some((x) => DELIVERY.includes(x)) ? "delivery" : null;
              return (
                <li
                  key={n}
                  className={`grid grid-cols-[2.5rem_1fr] gap-2 px-2 py-0.5 ${
                    tone === "objection" ? "bg-warn-wash" : tone === "delivery" ? "bg-ok-wash" : ""
                  }`}
                >
                  <span className="select-none text-right text-ink-300">{n}</span>
                  <span className="whitespace-pre-wrap break-words text-ink-900">
                    {line || " "}
                    {tags.length > 0 && (
                      <span className="ml-2 inline-flex flex-wrap gap-1 align-middle font-sans">
                        {tags.map((x) => (
                          <span key={x} className={`rounded px-1.5 text-[0.6875rem] font-medium ${OBJECTION.includes(x) ? "text-warn" : DELIVERY.includes(x) ? "text-ok" : "text-ink-600"}`}>
                            {tCode("msgtag", x, x)}
                          </span>
                        ))}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
          <p className="text-xs text-ink-500">{t("locker.chat.machine")}</p>
        </>
      )}
    </div>
  );
}
