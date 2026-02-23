
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
    context_analysis?: {
        technical_signal: { zh: string; en: string };
        macro_onchain: { zh: string; en: string };
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
        };
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

// ... (interfaces)

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
