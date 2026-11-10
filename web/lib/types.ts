export type Page<T> = { items: T[]; total: number };

export type Me = {
  id: string;
  email: string;
  tenant_id: string | null;
  role: string;
  tenant_name: string | null;
};

export type Member = {
  id: string;
  email: string;
  role: string;
  status: string;
  delivered?: boolean | null;
};

export type Debtor = {
  id: string;
  name: string;
  document: string;
  phone: string | null;
  phones?: string[];
  email: string | null;
  opt_out: boolean;
};

export type Match = {
  payment_id: string;
  invoice_id: string;
  amount_applied: string;
  method: string;
  score: number;
  provisional: boolean;
  confirmed_by: string;
};

export type Invoice = {
  id: string;
  external_id: string;
  description: string | null;
  amount: string;
  amount_paid: string;
  due_date: string;
  status: string;
  txid: string | null;
  parent_id: string | null;
  agreement_id: string | null;
  has_payment_code: boolean;
  debtor: Debtor;
};

export type Installment = {
  id: string;
  external_id: string;
  description: string | null;
  amount: string;
  due_date: string;
  status: string;
};

export type InvoiceDetail = Invoice & {
  dunning_events: { step: string; channel: string; sent_at: string; delivery_status: string }[];
  messages: Message[];
  promises: { promised_date: string; fulfilled: boolean | null; created_at: string }[];
  matches: Match[];
  installments: Installment[];
};

export type Payment = {
  id: string;
  origin: string;
  status: string;
  amount: string;
  paid_at: string;
  e2e_id: string | null;
  payer_doc: string | null;
  payer_name: string | null;
  payer_bank: string | null;
  has_receipt: boolean;
  bank_confirmed: boolean;
  extraction_confidence: number | null;
  matches: Match[];
  created_at: string;
};

export type Suggestion = {
  method: string;
  score: number;
  allocations: { invoice_id: string; amount: string }[];
};

export type ReceiptExtraction = {
  amount?: string | number | null;
  paid_at?: string | null;
  e2e_id?: string | null;
  payer_doc?: string | null;
  payer_name?: string | null;
  bank?: string | null;
  payee_name?: string | null;
  method?: string | null;
  confidence?: number | null;
};

export type ReviewException = {
  id: string;
  type: string;
  status: string;
  payment: Payment | null;
  invoice_id: string | null;
  conversation_id: string | null;
  details: {
    reason?: string;
    layer?: number;
    suggestions?: Suggestion[];
    debtor_id?: string;
    motivo?: string;
    problems?: string[];
    file_key?: string;
    content_type?: string;
    extraction?: ReceiptExtraction;
  };
  assignee: string | null;
  resolution: string | null;
  created_at: string;
  resolved_at: string | null;
};

export type Conversation = {
  id: string;
  debtor: Debtor;
  intent: string | null;
  state: string;
  summary: string | null;
  identity_verified: boolean;
  assigned_to: string | null;
  updated_at: string;
};

export type Message = {
  id: string;
  direction: string;
  author: string;
  body: string | null;
  invoice_id: string | null;
  delivery_status: string | null;
  file_status: string | null;
  created_at: string;
};

export type Delivery = {
  id: string;
  conversation_id: string;
  invoice_id: string | null;
  debtor_name: string;
  direction: string;
  body: string | null;
  delivery_status: string | null;
  file_status: string | null;
  created_at: string;
};

export type Approval = {
  id: string;
  conversation_id: string;
  debtor: Debtor;
  reason: string;
  payload: Record<string, unknown>;
  status: string;
  decided_by: string | null;
  created_at: string;
};

export type TenantSettings = {
  timezone: string;
  negotiation_policy: {
    max_discount_pct_cash: string;
    min_down_payment_pct: string;
    max_installments: number;
    min_installment_amount: string;
    installment_interval_days: number;
    monthly_interest_pct: string;
    first_due_in_days: number;
    max_promise_days: number;
  };
  dunning_rules: {
    steps: {
      key: string;
      offset: number;
      channels: string[];
      template: string | null;
      handoff: boolean;
    }[];
    templates: Record<string, string>;
    whatsapp_templates: Record<string, { name: string; language: string; params: string[] }>;
    rate_per_minute: number;
    text_version?: string;
  };
  allowed_hours: { start: string; end: string; weekdays: number[] };
  reconciliation_rules: {
    days_before_due: number;
    days_after_due: number;
    name_similarity_min: number;
    max_invoices_in_sum: number;
    allow_partial: boolean;
    max_overpay_pct: string;
    max_underpay_pct: string;
  };
  whatsapp_senders?: { instance: string; number: string }[];
  owner_email?: string;
  owner_phone?: string;
  legal_basis?: string;
  active?: boolean;
  missing?: string[];
};

export type Metrics = {
  period_start: string;
  period_end: string;
  recovery_rate: number | null;
  overdue_amount: string;
  recovered_amount: string;
  avg_days_late: number | null;
  baseline_avg_days_late: number | null;
  promises_made: number;
  promises_kept: number;
  promise_kept_rate: number | null;
  payments_reconciled: number;
  auto_reconciled: number;
  auto_reconciliation_rate: number | null;
  exceptions_open: number;
  avg_exception_resolution_hours: number | null;
};
