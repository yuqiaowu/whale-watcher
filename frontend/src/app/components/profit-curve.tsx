import { useEffect, useState, useRef } from 'react';
import { fetchNavHistory } from '@/lib/api';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useLanguage } from "@/app/i18n/LanguageContext";

interface ProfitCurveProps {
    hideStats?: boolean;
}

interface AnimatedDotProps {
    cx: number;
    cy: number;
    stroke: string;
}

const AnimatedDot = (props: AnimatedDotProps) => {
    const { cx, cy, stroke } = props;

    return (
        <g>
            <circle cx={cx} cy={cy} r={6} fill={stroke} opacity={0.3}>
                <animate
                    attributeName="r"
                    from="6"
                    to="12"
                    dur="1.5s"
                    begin="0s"
                    repeatCount="indefinite"
                />
                <animate
                    attributeName="opacity"
                    from="0.6"
                    to="0"
                    dur="1.5s"
                    begin="0s"
                    repeatCount="indefinite"
                />
            </circle>
            <circle cx={cx} cy={cy} r={4} fill={stroke} />
        </g>
    );
};

export function ProfitCurve({ hideStats = false }: ProfitCurveProps) {
    // Match the reference data roughly
    const generateChartData = () => {
        const points = [
            { date: '1/21 12:01', value: 10000, btcValue: 10000 },
            { date: '1/21 16:02', value: 9950, btcValue: 10050 },
            { date: '1/21 20:01', value: 9800, btcValue: 10020 },
            { date: '1/22 0:01', value: 9850, btcValue: 10100 },
            { date: '1/22 4:02', value: 9700, btcValue: 10150 },
            { date: '1/22 8:01', value: 9600, btcValue: 10180 },
            { date: '1/22 12:01', value: 9550, btcValue: 10220 },
            { date: '1/22 16:02', value: 9480, btcValue: 10190 },
            { date: '1/22 20:15', value: 9580, btcValue: 10250 },
        ];

        const data = [];
        // Interpolate to create a smooth curve
        for (let i = 0; i < points.length - 1; i++) {
            const start = points[i];
            const end = points[i + 1];
            for (let j = 0; j < 5; j++) { // Fewer points for smoother Recharts rendering
                const t = j / 5;
                // Cosine interpolation for smoothness
                const t2 = (1 - Math.cos(t * Math.PI)) / 2;
                data.push({
                    date: start.date,
                    value: start.value * (1 - t2) + end.value * t2,
                    btcValue: start.btcValue * (1 - t2) + end.btcValue * t2,
                });
            }
        }
        data.push(points[points.length - 1]);
        return data;
    };

    const [data, setData] = useState<any[]>([]);
    const scrollContainerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollContainerRef.current) {
            setTimeout(() => {
                if (scrollContainerRef.current) {
                    scrollContainerRef.current.scrollLeft = scrollContainerRef.current.scrollWidth;
                }
            }, 100);
        }
    }, [data]);

    useEffect(() => {
        console.log("ProfitCurve: Fetching nav history...");
        fetchNavHistory()
            .then(history => {
                console.log("ProfitCurve: History received", history?.length);
                if (history && history.length > 0) {
                    // Find first valid BTC price for normalization
                    const startBtcPrice = history.find(h => h.btc_price)?.btc_price || 1;
                    const initialNav = history[0].nav;

                    // Format data with safer date parsing
                    const formatted = history.map((h, idx) => {
                        let dateStr = h.timestamp;
                        try {
                            const dateObj = new Date(dateStr);
                            if (!isNaN(dateObj.getTime())) {
                                // Format as MM/DD HH:mm
                                const month = (dateObj.getMonth() + 1).toString().padStart(2, '0');
                                const day = dateObj.getDate().toString().padStart(2, '0');
                                const hours = dateObj.getHours().toString().padStart(2, '0');
                                const minutes = dateObj.getMinutes().toString().padStart(2, '0');
                                dateStr = `${month}/${day} ${hours}:${minutes}`;
                            } else {
                                dateStr = h.timestamp.slice(5, 16).replace('-', '/');
                            }
                        } catch (e) {
                            dateStr = h.timestamp.substring(5, 10);
                        }

                        // Calculate normalized BTC value
                        const btcNormalized = h.btc_price
                            ? initialNav * (h.btc_price / startBtcPrice)
                            : null;

                        return {
                            id: idx, // Explicit ID for Recharts if needed
                            date: dateStr,
                            value: h.nav,
                            btcValue: btcNormalized || h.nav
                        };
                    });

                    // Filter out NaNs
                    const cleanData = formatted.filter(d => !isNaN(d.value));

                    // Downsample data for smoother chart if too many points
                    const targetPoints = 200;
                    const samplingRate = Math.max(1, Math.floor(cleanData.length / targetPoints));
                    const downsampled = cleanData.filter((_, index) => index % samplingRate === 0);

                    // Always include the last point for accuracy
                    if (downsampled.length > 0 && downsampled[downsampled.length - 1] !== cleanData[cleanData.length - 1]) {
                        downsampled.push(cleanData[cleanData.length - 1]);
                    }

                    console.log("ProfitCurve: Setting data", downsampled.length);
                    setData(downsampled);
                } else {
                    console.warn("ProfitCurve: No history data, using fallback");
                    setData(generateChartData()); // Fallback
                }
            })
            .catch((e) => {
                console.error("ProfitCurve: Fetch error", e);
                setData(generateChartData());
            });
    }, []);

    // Helper to calculate nice domain
    const values = data.flatMap(d => [d.value, d.btcValue]);
    let dataMin = Math.min(...values);
    let dataMax = Math.max(...values);
    // Safety check if min == max (flat line) or Infinity (no data)
    if (!isFinite(dataMin) || !isFinite(dataMax)) {
        dataMin = 9000;
        dataMax = 11000;
    } else if (dataMin === dataMax) {
        dataMin = dataMin * 0.95;
        dataMax = dataMax * 1.05;
    } else {
        const padding = (dataMax - dataMin) * 0.1;
        dataMin = Math.floor(dataMin - padding);
        dataMax = Math.ceil(dataMax + padding);
    }

    const chartColor = '#39FF14'; // Fluorescent Green
    const btcColor = '#6B7280'; // Gray for benchmark

    // Calculate BTC ROI for the display
    const initialBtcNorm = data.length > 0 ? data[0].btcValue : 10000;
    const finalBtcNorm = data.length > 0 ? data[data.length - 1].btcValue : 10000;

    // Calculate BTC ROI based on the actual price change from start to end
    const btcRoi = initialBtcNorm !== 0 ? ((finalBtcNorm - initialBtcNorm) / initialBtcNorm) * 100 : 0;

    // Calculate Strategy ROI to detect if identical (fallback data)
    const initialNav = data.length > 0 ? data[0].value : 10000;
    const finalNav = data.length > 0 ? data[data.length - 1].value : 10000;
    const strategyRoi = initialNav !== 0 ? ((finalNav - initialNav) / initialNav) * 100 : 0;

    // Auto-hide benchmark if identical to strategy (meaning data is missing/fallback)
    const isIdentical = Math.abs(strategyRoi - btcRoi) < 0.01;
    const showBenchmark = !hideStats && !isIdentical;

    const { t } = useLanguage();

    return (
        <div className="h-full w-full min-h-[300px] relative p-0 flex flex-col">
            {/* Benchmark Yield Indicator */}
            {showBenchmark && (
                <div className="absolute top-2 right-4 z-20 flex items-center gap-2 bg-[#0a0e1a]/90 backdrop-blur-md px-3 py-1.5 rounded border border-[#2D3139]/50 shadow-lg">
                    <div className="w-2 h-0.5 bg-[#6B7280]"></div>
                    <span className="text-[10px] text-[#8E9297]">{t.aiTrading.btcBenchmark}</span>
                    <span className="text-xs font-mono font-bold text-[#39FF14]">{btcRoi > 0 ? '+' : ''}{btcRoi.toFixed(2)}%</span>
                </div>
            )}

            <div className="relative flex-1 min-h-0 w-full">
                {/* 1. Fixed Y-Axis Layer (Absolute Left) */}
                <div className="absolute left-0 top-0 bottom-0 w-[60px] z-20 bg-[#0a0e1a]/80 border-r border-[#374151] backdrop-blur-[2px] pointer-events-none">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={data} margin={{ top: 20, right: 0, left: 0, bottom: 20 }}>
                            <YAxis
                                domain={[dataMin, dataMax]}
                                axisLine={false}
                                tickLine={false}
                                tick={{ fill: '#8E9297', fontSize: 10, fontWeight: 500 }}
                                tickFormatter={(value) => `$${value.toLocaleString()}`}
                                width={60}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>

                {/* 2. Scrollable Content Layer */}
                <div ref={scrollContainerRef} className="absolute inset-0 overflow-x-auto no-scrollbar pl-[60px]">
                    <div style={{ width: `${Math.max(1000, data.length * 15)}px`, height: '100%' }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={data} margin={{ top: 20, right: 30, left: 0, bottom: 20 }}>
                                <defs>
                                    <linearGradient id="colorLoss" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={chartColor} stopOpacity={0.3} />
                                        <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="colorBtc" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={btcColor} stopOpacity={0.1} />
                                        <stop offset="95%" stopColor={btcColor} stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid
                                    strokeDasharray="3 3"
                                    stroke="#374151"
                                    opacity={0.4}
                                />
                                <XAxis
                                    dataKey="date"
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{ fill: '#8E9297', fontSize: 10, fontWeight: 500 }}
                                    dy={10}
                                />
                                <YAxis
                                    domain={[dataMin, dataMax]}
                                    width={0}
                                    axisLine={false}
                                    tick={false}
                                />
                                <ReferenceLine y={10000} stroke="#8E9297" strokeDasharray="3 3" opacity={0.5} />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: '#0a0e1a',
                                        border: `1px solid ${chartColor}`,
                                        borderRadius: '4px',
                                        color: '#fff',
                                        fontSize: '12px',
                                        fontFamily: 'monospace'
                                    }}
                                    itemStyle={{ color: chartColor }}
                                    formatter={(value: number, name: string) => [
                                        `$${value.toLocaleString()}`,
                                        name === 'value'
                                            ? t.aiTrading.currentValue
                                            : t.aiTrading.btcBenchmark
                                    ]}
                                    labelStyle={{ color: '#8E9297', marginBottom: '0.25rem' }}
                                />

                                {showBenchmark && (
                                    <Area
                                        type="basis"
                                        dataKey="btcValue"
                                        stroke={btcColor}
                                        strokeWidth={2}
                                        strokeDasharray="4 4"
                                        fill="url(#colorBtc)"
                                        activeDot={false}
                                        dot={(props) => {
                                            const { index, cx, cy } = props;
                                            if (index === data.length - 1) {
                                                return <circle cx={cx} cy={cy} r={3} fill={btcColor} />;
                                            }
                                            return <></>;
                                        }}
                                    />
                                )}

                                <Area
                                    type="basis"
                                    dataKey="value"
                                    stroke={chartColor}
                                    strokeWidth={2}
                                    fill="url(#colorLoss)"
                                    activeDot={{ r: 6, fill: chartColor }}
                                    dot={(props: { cx: number; cy: number; index: number }) => {
                                        const { index, cx, cy } = props;
                                        // Only render dot for the last data point
                                        if (index === data.length - 1) {
                                            return <AnimatedDot key={index} cx={cx} cy={cy} stroke={chartColor} />;
                                        }
                                        return <g />;
                                    }}
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
}
