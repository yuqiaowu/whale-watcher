
const getBaseUrl = () => {
    // If it's a Vercel/Production build, use the VITE_API_URL if it exists
    if (typeof process !== 'undefined' && process.env.VITE_API_URL) {
        return process.env.VITE_API_URL;
    }
    // For Vite client-side environment variables
    const viteUrl = import.meta.env.VITE_API_URL;
    if (viteUrl) {
        return viteUrl.endsWith('/api') ? viteUrl : `${viteUrl}/api`;
    }
    return 'http://localhost:5001/api';
};

export const API_BASE_URL = getBaseUrl();


export interface PortfolioSummary {
    nav: number;
    totalPnl: number;
    pnlPercent: number;
    startTime: string;
    initialNav: number;
    winRate: number;
    totalTrades: number;
}

export interface Position {
    symbol: string;
    name: string;
    entryPrice: number;
    currentPrice: number;
    stopLoss: number;
    takeProfit: number;
    amount: number | string;
    margin?: number;
    marginUsd?: number;
    notionalUsd?: number;
    pnl: number;
    pnlPercent: number;
    type: string;
    leverage: number;
}

export interface TradeHistory {
    id: string;
    symbol: string;
    type: string;
    entryPrice: number;
    exitPrice: number;
    amount: number;
    pnl: number;
    pnlPercent: number;
    entryTime: string;
    exitTime: string;
    leverage: number;
}

export interface AgentDecision {
    analysis_summary: { zh: string; en: string };
    confidence_probability?: number;
    red_team_audit?: { zh: string; en: string };
    context_analysis?: {
        technical_signal: { zh: string; en: string };
        macro_onchain: { zh: string; en: string };
        quantitative_analysis?: { zh: string; en: string };
        regime_safety?: { zh: string; en: string };
        portfolio_status: { zh: string; en: string };
        reflection: { zh: string; en: string };
    };
    actions: Array<{
        action: string;
        symbol: string;
        entry_reason: { zh: string; en: string }; // Changed from reason
        exit_plan?: {
            take_profit?: number;
            stop_loss?: number;
            invalidation?: { zh: string; en: string };
        };
        original_invalidation_rule?: string;
        price?: number;
        amount?: number;
    }>;
    timestamp?: string;
}

export interface NavPoint {
    timestamp: string;
    nav: number;
    btc_price?: number;
}

export interface QlibFreshness {
    fresh?: boolean;
    expected_completed_bar?: string | null;
    payload_as_of?: string | null;
    model_trained_at?: string | null;
    model_train_end?: string | null;
    model_is_fresh?: boolean | null;
    model_freshness_reason?: string | null;
    payload_symbols?: string[];
    missing_payload_symbols?: string[];
    csv_latest_by_symbol?: Record<string, string | null>;
    stale_csv_symbols?: string[];
    reasons?: string[];
}

export interface V2LatestCycle {
    cycleId?: string;
    generated_at?: string;
    generated_at_local?: string;
    cycle_local_time?: string;
    timeframe?: string;
    decision_mode?: 'model_decision' | 'candidate_blueprint' | string;
    qlib_freshness?: QlibFreshness;
    snapshots?: Record<string, any>[];
    candidate_batches?: Record<string, any>[];
    rule_evaluations?: Record<string, any>[];
    research_outputs?: Array<Record<string, any> | null>;
    risk_reviews?: Record<string, any>[];
    executions?: Record<string, any>[];
    record_count?: number;
    post_trade_review?: Record<string, any> | null;
}

export interface V2TradeRecord {
    decisionId?: string;
    cycleId?: string;
    symbol?: string;
    timeframe?: string;
    positionState?: string;
    snapshot?: Record<string, any>;
    marketState?: Record<string, any> | null;
    modelDecision?: {
        schema_version?: string;
        action?: 'BUY' | 'SELL' | 'WAIT' | 'HOLD' | string;
        direction?: 'LONG' | 'SHORT' | 'FLAT' | string;
        confidence?: number;
        setup_type?: string;
        risk_level?: string;
        horizon?: string;
        reason_codes?: string[];
        invalid_if?: string[];
        invalidation_rules?: Record<string, any>[];
        summary?: string;
        model_role?: string;
        llm_audit?: Record<string, any>;
        verifier?: Record<string, any>;
    } | null;
    candidate?: {
        generation_mode?: 'model_decision' | string;
        candidate_proposals?: Record<string, any>[];
        model_decision_diagnostic?: Record<string, any>;
        qlib_freshness?: QlibFreshness;
        [key: string]: any;
    };
    ruleEvaluation?: Record<string, any>;
    researchOutput?: Record<string, any> | null;
    riskReview?: Record<string, any>;
    execution?: Record<string, any>;
    provenance?: Record<string, any>;
    created_at?: string;
    updated_at?: string;
}

export interface ApiHealth {
    status?: string;
    version?: string;
    mongo_connected?: boolean;
    latest_run_status?: string;
    latest_run_at?: string;
    latest_cycle_id?: string;
}

export interface MarketStats {
    fed_futures?: {
        implied_rate: number;
        change_5d_bps: number;
        price: number;
        trend: string;
    };
    fear_greed?: {
        latest?: {
            value: string;
            value_classification: string;
        }
    };
    market_indices?: {
        dxy?: { value: number; change_pct: number; timestamp: string; };
        us10y?: { value: number; change_pct: number; timestamp: string; };
        vix?: { value: number; change_pct: number; timestamp: string; };
    };
    [key: string]: any;
}

export interface CryptoDataResponse {
    data: Record<string, {
        price: number;
        rsi_4h: number;
        funding_rate: number;
        funding_rate_status: string;
        volume_24h: number;
        sentiment: string;
        sentimentScore: number;
        [key: string]: any;
    }>;
    lastUpdated: number;
}

export async function fetchSummary(): Promise<PortfolioSummary> {
    const res = await fetch(`${API_BASE_URL}/summary`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch summary');
    return res.json();
}

export async function fetchPositions(): Promise<Position[]> {
    const res = await fetch(`${API_BASE_URL}/positions`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch positions');
    return res.json();
}

export async function fetchHistory(): Promise<TradeHistory[]> {
    const res = await fetch(`${API_BASE_URL}/history`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch history');
    return res.json();
}

export async function fetchAgentDecision(): Promise<AgentDecision[]> {
    const res = await fetch(`${API_BASE_URL}/agent-decision`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch agent decision');
    return res.json();
}

export async function fetchNavHistory(): Promise<NavPoint[]> {
    const res = await fetch(`${API_BASE_URL}/nav-history`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch nav history');
    return res.json();
}

export async function fetchMarketStats(): Promise<MarketStats> {
    const res = await fetch(`${API_BASE_URL}/market-stats`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch market stats');
    return res.json();
}

export async function fetchCryptoData(): Promise<CryptoDataResponse> {
    const res = await fetch(`${API_BASE_URL}/crypto-data`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch crypto data');
    return res.json();
}

export async function fetchLatestV2Cycle(): Promise<V2LatestCycle> {
    const res = await fetch(`${API_BASE_URL}/v2/latest-cycle`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch latest v2 cycle');
    return res.json();
}

export async function fetchV2TradeRecords(): Promise<V2TradeRecord[]> {
    const res = await fetch(`${API_BASE_URL}/v2/trade-records`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch v2 trade records');
    return res.json();
}

export async function fetchLatestV2TradeRecord(): Promise<V2TradeRecord> {
    const res = await fetch(`${API_BASE_URL}/v2/latest-trade-record`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch latest v2 trade record');
    return res.json();
}

export async function fetchApiHealth(): Promise<ApiHealth> {
    const res = await fetch(`${API_BASE_URL}/health`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch API health');
    return res.json();
}
