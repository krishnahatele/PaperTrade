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
  created_at: string;
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
