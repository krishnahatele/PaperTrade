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
  role: string;
  trade_plan_id: string | null;
  trigger_price: string | null;
  status_message: string | null;
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
  llm: { provider: string; model: string; api_key: SecretField };
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
  llm_base_url: string | null;
};

export type LLMProviderInfo = {
  id: string;
  label: string;
  base_url: string | null;
  needs_key: boolean;
  key_hint: string;
  note: string;
  suggested_models: string[];
  key_set: boolean;
  active: boolean;
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

export type TradePlan = {
  id: string;
  signal_id: string | null;
  broker_account_id: string;
  instrument_id: string;
  tradingsymbol: string | null;
  side: "BUY" | "SELL";
  product: string;
  quantity: number;
  status: "pending" | "open" | "closed" | "cancelled";
  planned_entry: string | null;
  stop_loss: string;
  initial_stop_loss: string | null;
  target: string | null;
  targets: TargetLeg[];
  trailing: { mode?: TrailMode; value?: string };
  open_quantity: number;
  best_price: string | null;
  entry_price: string | null;
  exit_price: string | null;
  gross_pnl: string | null;
  realized_pnl: string | null;
  unrealized_pnl: string | null;
  exchange: string | null;
  segment: string | null;
  lot_size: number | null;
  ltp: string | null;
  charges: string;
  exit_reason: string | null;
  opened_at: string | null;
  closed_at: string | null;
  created_at: string;
};

export type PositionView = {
  id: string;
  broker_account_id: string;
  instrument_id: string;
  tradingsymbol: string;
  product: string;
  quantity: number;
  average_price: string;
  realized_pnl: string;
  ltp: string | null;
  unrealized_pnl: string | null;
};

export type AccountSummary = {
  broker_account_id: string;
  label: string;
  mode: string;
  capital: string;
  realized_today: string;
  realized_total: string;
  unrealized: string;
  open_trades: number;
  pending_trades: number;
  closed_trades: number;
  win_rate: string | null;
};

export type BrokerAccount = {
  id: string;
  broker: string;
  label: string;
  mode: string;
  is_active: boolean;
  settings: Record<string, string | number | boolean>;
};

export type KiteStatus = { configured: boolean; session_active: boolean; user_id: string | null };

export type TrailMode = "none" | "step" | "points" | "percent";
export type TargetLeg = { price: string; quantity: number; status: "open" | "hit" | "cancelled" };

// ------------------------------------------------------------------ brokers
export type CredentialField = { name: string; label: string; secret_name: string; secret: boolean; placeholder: string; help: string };
export type BrokerCapabilities = Record<
  | "place_orders" | "modify_orders" | "broker_bracket" | "broker_trailing" | "positions" | "funds"
  | "exit_all" | "kill_switch" | "market_data" | "historical" | "expired_options",
  boolean
>;
export type BrokerInfo = {
  id: string;
  label: string;
  available: boolean;
  description: string;
  fields: CredentialField[];
  login_note: string;
  capabilities: BrokerCapabilities;
  static_ip_required: boolean;
  costs: string;
  docs_url: string | null;
};
export type BrokerStatus = {
  info: BrokerInfo;
  configured: boolean;
  session_active: boolean;
  fields: { name: string; set: boolean; hint: string | null }[];
  selected: boolean;
};
export type DataSource = "auto" | "kite" | "dhan" | "manual";
export type BrokerRuntime = { primary: string; market_data: DataSource; history: DataSource; dhan_token_saved_at: string | null };
export type BrokerPosition = { exchange: string; tradingsymbol: string; product: string; quantity: number; average_price: string };
export type ConnectionTest = {
  ok: boolean;
  provider: string;
  profile: { user_id: string; name: string | null; detail: Record<string, string> } | null;
  funds: { available: string; used: string | null; detail: Record<string, string> } | null;
  positions: BrokerPosition[];
  error: string | null;
  notes: string[];
};

// --------------------------------------------------------------------- bot
export type BotNotify = { signals: boolean; trades: boolean; skipped: boolean; news: boolean; market_moves: boolean };
export type BotStatus = {
  configured: boolean;
  running: boolean;
  username: string | null;
  linked: boolean;
  owner_name: string | null;
  last_error: string | null;
  notify: BotNotify;
};

// -------------------------------------------------------------------- news
export type NewsItem = {
  id: string;
  source: string;
  title: string;
  summary: string | null;
  url: string;
  published_at: string;
  matched: string[];
  direction: "up" | "down" | null;
};
export type AlertItem = {
  id: string;
  kind: "news" | "market" | "system";
  title: string;
  body: string | null;
  url: string | null;
  payload: Record<string, unknown>;
  read: boolean;
  created_at: string;
};
export type Feed = { name: string; url: string; enabled: boolean };
export type Watch = { symbol: string; label: string; threshold_pct: string; window_minutes: number; enabled: boolean };
export type NewsSettings = {
  enabled: boolean;
  poll_minutes: number;
  feeds: Feed[];
  keywords: string[];
  watches: Watch[];
  market_alerts: boolean;
  alert_cooldown_minutes: number;
};
export type WatchState = {
  symbol: string;
  label: string;
  tradingsymbol: string | null;
  ltp: string | null;
  change_pct: string | null;
  window_minutes: number;
  threshold_pct: string;
};

// ------------------------------------------------------------------ replay
export type ReplayStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type ReplayOutcome = "win" | "loss" | "breakeven" | "entry_not_hit" | "no_data" | "unresolved" | "incomplete" | "not_signal";
export type ReplayStats = {
  signals: number;
  traded: number;
  wins: number;
  losses: number;
  breakeven: number;
  entry_not_hit: number;
  no_data: number;
  unresolved: number;
  incomplete: number;
  win_rate: string | null;
  accuracy_t1: string | null;
  net_pnl: string;
  avg_win: string | null;
  avg_loss: string | null;
  profit_factor: string | null;
  expectancy: string | null;
  avg_r: string | null;
};
export type ReplayBrief = { id: string; symbol: string | null; source: string; net_pnl: string; exit_reason: string | null; message_at: string };
export type ReplayReport = {
  generated_at: string;
  messages_scanned: number;
  message_origin?: string;
  overall: ReplayStats;
  capital_start: string;
  capital_end: string;
  return_pct: string | null;
  max_drawdown: string;
  max_drawdown_pct: string | null;
  max_consecutive_losses: number;
  avg_holding_minutes: number | null;
  targets_hit: Record<string, { count: number; pct: string | null }>;
  by_source: Record<string, ReplayStats>;
  by_segment: Record<string, ReplayStats>;
  by_side: Record<string, ReplayStats>;
  by_exit_reason: Record<string, ReplayStats>;
  by_day: Record<string, ReplayStats>;
  by_hour: Record<string, ReplayStats>;
  by_underlying: Record<string, ReplayStats>;
  equity_curve: { t: string | null; equity: string; symbol?: string | null }[];
  best_trades: ReplayBrief[];
  worst_trades: ReplayBrief[];
  data_sources: Record<string, number>;
};
export type ReplayRun = {
  id: string;
  name: string;
  status: ReplayStatus;
  params: Record<string, unknown>;
  progress: { stage?: string; messages?: number; done?: number; signals?: number; origin?: string; price_sources?: string[] };
  report: ReplayReport | Record<string, never>;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
};
export type ReplayRunBrief = Omit<ReplayRun, "params" | "report"> & { overall: ReplayStats | null };
export type ReplayTrade = {
  id: string;
  run_id: string;
  source_name: string;
  message_text: string;
  message_at: string;
  outcome: ReplayOutcome;
  tradingsymbol: string | null;
  segment: string | null;
  side: "BUY" | "SELL" | null;
  signal: Record<string, unknown>;
  quantity: number | null;
  entry_price: string | null;
  entry_at: string | null;
  exit_price: string | null;
  exit_at: string | null;
  exit_reason: string | null;
  targets_hit: number;
  gross_pnl: string | null;
  charges: string | null;
  net_pnl: string | null;
  r_multiple: string | null;
  mfe: string | null;
  mae: string | null;
  legs: TargetLeg[];
  notes: string | null;
};
