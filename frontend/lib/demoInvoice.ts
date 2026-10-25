// A demo invoice that falls due in a few days, so both options are open when a judge
// tries it. Built from the bundled CASE-01 input with its dates moved: only inputs are
// set here; the engine and the server decide the due date and work out every figure.
// The delivery date is chosen so the due date lands about four days ahead, which is the
// tenor the saved sample bids (used by the Option 1 demo) were priced for.
const DAYS_SINCE_DELIVERY = 41;

import { getPresetRequest } from "./api";
import type { CaseRequest } from "./types";

/** Local calendar date `daysAgo` days back, as YYYY-MM-DD. */
function localDate(daysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export async function demoInvoiceRequest(): Promise<CaseRequest> {
  const base = (await getPresetRequest("case_01")).data.request;
  const delivered = localDate(DAYS_SINCE_DELIVERY);
  return {
    ...base,
    transaction: {
      ...base.transaction,
      contract_date: localDate(DAYS_SINCE_DELIVERY + 14),
      supply_date: delivered,
      invoice_date: delivered,
      delivery_date: delivered,
      calculation_date: localDate(0),
    },
    objections: [],
    part_payments: [],
    acknowledgments: [],
  };
}
