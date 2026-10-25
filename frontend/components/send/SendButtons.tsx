"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import { Icon } from "../common/Icon";

const PHONE = /^\d{8,15}$/;

/** An empty number is fine (the owner picks the contact in WhatsApp); a typed one must look like digits. */
export function isPhoneValid(phone: string): boolean {
  return phone === "" || PHONE.test(phone);
}

/**
 * Open in WhatsApp, open in email, copy: the three ways a draft leaves this
 * app, all through the owner's own apps. Nothing is sent from here; every
 * action stays off until `enabled` (the draft was reviewed).
 */
export function SendButtons({
  text,
  subject,
  phone,
  email,
  enabled,
  channels = true,
  copyPrimary = false,
  onPrepared,
}: {
  text: string;
  subject: string;
  phone: string;
  email: string;
  enabled: boolean;
  /** false hides WhatsApp and email (a checklist has no recipient). */
  channels?: boolean;
  copyPrimary?: boolean;
  /** Called when the owner opens an app or copies, so the case can log "prepared". */
  onPrepared?: () => void;
}) {
  const { t } = useT();
  const [copied, setCopied] = useState(false);
  const phoneValid = isPhoneValid(phone);
  const waHref = `https://wa.me/${phoneValid ? phone : ""}?text=${encodeURIComponent(text)}`;
  const mailHref = `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      onPrepared?.();
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <>
      {channels && (
        <>
          <a
            href={enabled && phoneValid ? waHref : undefined}
            aria-disabled={!enabled || !phoneValid}
            target="_blank"
            rel="noreferrer noopener"
            onClick={(e) => (enabled && phoneValid ? onPrepared?.() : e.preventDefault())}
            className="btn btn-primary"
          >
            <Icon name="send" className="h-4 w-4" />
            {t("send.open_whatsapp")}
          </a>
          <a
            href={enabled ? mailHref : undefined}
            aria-disabled={!enabled}
            onClick={(e) => (enabled ? onPrepared?.() : e.preventDefault())}
            className="btn btn-secondary"
          >
            <Icon name="doc" className="h-4 w-4" />
            {t("send.open_email")}
          </a>
        </>
      )}
      <button type="button" className={`btn ${copyPrimary ? "btn-primary" : "btn-secondary"}`} disabled={!enabled} onClick={copy}>
        <Icon name="copy" className="h-4 w-4" />
        {copied ? t("send.copied") : t("send.copy")}
      </button>
    </>
  );
}
