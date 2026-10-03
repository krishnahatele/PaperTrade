export type Instrument = {
  id: string;
  exchange: string;
  tradingsymbol: string;
  name: string | null;
  instrument_type: string;
  instrument_token: number | null;
  expiry: string | null;
  strike: string | null;
  lot_size: number;
  tick_size: string;
  is_active: boolean;
  created_at: string;
};

export type SignalSource = {
  id: string;
  kind: "telegram" | "manual" | "webhook";
  name: string;
  external_id: string | null;
  is_enabled: boolean;
  created_at: string;
};

export type Signal = {
  id: string;
  source_id: string;
  instrument_id: string | null;
  symbol_text: string;
  side: "BUY" | "SELL";
  entry_low: string | null;
  entry_high: string | null;
  stop_loss: string | null;
  targets: string[];
  confidence: string | null;
  status: string;
  parser: string;
  raw_message_id: string | null;
  notes: string | null;
  details: { underlying?: string | null; instrument_type?: string | null; strike?: string | null; expiry_text?: string | null; warnings?: string[]; llm_error?: string };
  created_at: string;
};

export type ParsePreview = {
  parser: string | null;
  is_signal: boolean;
  reason: string | null;
  side: string | null;
  symbol_text: string | null;
  instrument_type: string | null;
  entry_low: string | null;
  entry_high: string | null;
  stop_loss: string | null;
  targets: string[];
  confidence: string;
  warnings: string[];
  llm_error: string | null;
  instrument_tradingsymbol: string | null;
};

export type Order = {
  id: string;
  instrument_id: string;
  client_order_id: string;
  mode: string;
  side: string;
  order_type: string;
  product: string;
  quantity: number;
  price: string | null;
  status: string;
  filled_quantity: number;
  average_price: string | null;
  created_at: string;
};

export type Position = {
  id: string;
  broker_account_id: string;
  instrument_id: string;
  product: string;
  quantity: number;
  average_price: string;
  realized_pnl: string;
  updated_at: string;
};

export type EventRecord = {
  id: string;
  event_type: string;
  aggregate_type: string | null;
  aggregate_id: string | null;
  payload: Record<string, unknown>;
  correlation_id: string | null;
  occurred_at: string;
};

export type SecretField = { set: boolean; hint: string | null };

export type Integrations = {
  telegram: { api_id: SecretField; api_hash: SecretField; phone: SecretField; authorized: boolean };
  kite: { api_key: SecretField; api_secret: SecretField; session_active: boolean; user_id: string | null };
  llm: { api_key: SecretField };
};

export type TradingRuntime = {
  kill_switch: boolean;
  auto_execute: boolean;
  live_armed: boolean;
  min_confidence: string;
  signal_ttl_minutes: number;
};

export type ParsingRuntime = {
  mode: "rules_only" | "rules_then_llm" | "llm_only";
  llm_model: string;
  llm_provider: string;
};

export type RuntimeSettings = { trading: TradingRuntime; parsing: ParsingRuntime };

export type TelegramStatus = {
  configured: boolean;
  authorized: boolean;
  listening: boolean;
  channels: number;
  login_step: "code" | "password" | "done" | null;
  messages_received: number;
  last_message_at: string | null;
  last_error: string | null;
};

export type TelegramChannel = {
  id: string;
  title: string;
  username: string | null;
  kind: string;
  source_id: string | null;
  source_enabled: boolean | null;
};

export type RawMessage = {
  id: string;
  source_id: string;
  external_message_id: string;
  content: string;
  received_at: string;
  status: string;
};
