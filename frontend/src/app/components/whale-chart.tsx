import { motion } from "motion/react";
import { LineChart, Line, AreaChart, Area, BarChart, Bar, ComposedChart, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface ChartData {
  name: string;
  value: number;
  volume?: number;
  volatility?: number;
  long?: number;
  short?: number;
  leverage?: number;
}

interface WhaleChartProps {
  title: string;
  subtitle?: string;
  type: 'line' | 'area' | 'bar' | 'mixed' | 'composed';
  data: ChartData[];
  color?: string;
  index: number;
  seriesNames?: {
    value?: string;
    volume?: string;
    volatility?: string;
    long?: string;
    short?: string;
    leverage?: string;
  };
}

export function WhaleChart({
  title,
  subtitle,
  type,
  data = [],
  color = '#39FF14',
  index,
  seriesNames
}: WhaleChartProps) {
  const chartData = data;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      // Find the index of the current point to calculate the delta from previous
      const currentIndex = chartData.findIndex(item => item.name === label);

      return (
        <div className="bg-[#0f172a] border border-[#39FF14]/50 p-3 shadow-2xl backdrop-blur-md rounded-sm">
          <p className="text-[#8E9297] text-[10px] mb-2 font-mono border-b border-[#2D3139] pb-1">{label}</p>
          {payload.map((entry: any, i: number) => {
            let changeText = null;
            if (currentIndex > 0) {
              const prevValue = chartData[currentIndex - 1][entry.dataKey as keyof ChartData] as number;
              const currValue = entry.value;

              if (typeof prevValue === 'number' && typeof currValue === 'number' && prevValue !== 0) {
                const diff = currValue - prevValue;
                const percent = ((diff / Math.abs(prevValue)) * 100).toFixed(2);
                const isPositive = diff > 0;
                const isNeutral = diff === 0;

                if (!isNeutral) {
                  changeText = (
                    <span className={`text-[10px] ml-auto pl-4 font-mono ${isPositive ? 'text-[#39FF14]' : 'text-[#FF3131]'}`}>
                      {isPositive ? '▲' : '▼'} {Math.abs(Number(percent))}%
                    </span>
                  );
                }
              }
            }

            return (
              <div key={i} className="flex items-center gap-2 mb-1 last:mb-0 min-w-[160px]">
                <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: entry.color || entry.stroke || entry.fill }}></div>
                <span className="text-gray-400 text-[11px] font-mono leading-none">{entry.name}:</span>
                <span className="text-[#E8E8E8] text-[12px] font-mono font-medium leading-none ml-1">
                  {typeof entry.value === 'number' ? entry.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : entry.value}
                </span>
                {changeText}
              </div>
            );
          })}
        </div>
      );
    }
    return null;
  };

  if (!chartData || chartData.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: index * 0.1 }}
        className="relative bg-[#1a1a1a] border border-[#2D3139] p-5 h-[280px] flex flex-col group"
      >
        <div className="mb-4">
          <h3 className="text-base font-mono font-medium text-[#E8E8E8] mb-1 tracking-wide">{title}</h3>
          {subtitle && (
            <p className="text-xs font-sans text-[#8E9297]">{subtitle}</p>
          )}
        </div>
        <div className="flex-1 flex items-center justify-center border border-dashed border-[#2a2f3e] rounded">
          <span className="text-[#8E9297] text-xs font-mono">No data available</span>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      whileHover={{
        scale: 1.02,
        boxShadow: "0 0 30px rgba(57, 255, 20, 0.2)"
      }}
      className="relative bg-[#1a1a1a] border border-[#2D3139] p-5 overflow-hidden group"
    >
      {/* Title */}
      <div className="mb-4">
        <h3 className="text-base font-mono font-medium text-[#E8E8E8] mb-1 tracking-wide">{title}</h3>
        {subtitle && (
          <p className="text-xs font-sans text-[#8E9297]">{subtitle}</p>
        )}
      </div>

      {/* Chart */}
      <div className="h-48 w-full" style={{ minHeight: '192px' }}>
        <ResponsiveContainer width="100%" height="100%" minHeight={192}>
          {type === 'line' ? (
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3e" />
              <XAxis
                dataKey="name"
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              <YAxis
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                name={seriesNames?.value || "Value"}
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={2}
                dot={{ fill: color, r: 4 }}
                activeDot={{ r: 6, fill: color, strokeWidth: 2, stroke: '#0a0e17' }}
              />
            </LineChart>
          ) : type === 'area' ? (
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id={`gradient-${index}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3e" />
              <XAxis
                dataKey="name"
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              <YAxis
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                name={seriesNames?.value || "Value"}
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={2}
                fill={`url(#gradient-${index})`}
              />
            </AreaChart>
          ) : type === 'mixed' ? (
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3e" />
              <XAxis
                dataKey="name"
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              <YAxis
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar
                dataKey={chartData[0]?.long !== undefined ? "long" : "value"}
                name={seriesNames?.long || seriesNames?.value || "Long / Value"}
                fill="#39FF14"
                stackId="a"
                barSize={12}
              />
              <Bar
                dataKey={chartData[0]?.short !== undefined ? "short" : "volume"}
                name={seriesNames?.short || seriesNames?.volume || "Short / Volume"}
                fill="#FF3131"
                stackId="a"
                barSize={12}
              />
            </BarChart>
          ) : type === 'composed' ? (
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3e" />
              <XAxis
                dataKey="name"
                stroke="#8E9297"
                minTickGap={15}
                interval="preserveStartEnd"
                style={{ fontSize: '10px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297', fontSize: 10 }}
              />
              <YAxis
                yAxisId="left"
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              {(chartData[0]?.volatility !== undefined || (chartData[0]?.leverage !== undefined && chartData[0]?.long === undefined)) && (
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  stroke="#39FF14"
                  style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                  tick={{ fill: '#39FF14' }}
                />
              )}
              <Tooltip content={<CustomTooltip />} />
              {chartData[0]?.long !== undefined ? (
                <>
                  <Bar yAxisId="left" dataKey="long" name={seriesNames?.long || "Long"} fill="#39FF14" stackId="a" barSize={12} />
                  <Bar yAxisId="left" dataKey="short" name={seriesNames?.short || "Short"} fill="#FF3131" stackId="a" barSize={12} />
                </>
              ) : (
                <Bar yAxisId="left" dataKey="value" name={seriesNames?.volume || "Volume"} fill="#4A4A4A66" barSize={12} />
              )}
              {chartData[0]?.volatility !== undefined && (
                <Line
                  yAxisId="right"
                  name={seriesNames?.volatility || "NATR"}
                  type="monotone"
                  dataKey="volatility"
                  stroke="#39FF14"
                  strokeWidth={2}
                  dot={{ fill: '#39FF14', r: 4 }}
                  activeDot={{ r: 6, fill: '#39FF14', strokeWidth: 2, stroke: '#0a0e17' }}
                />
              )}
              {chartData[0]?.leverage !== undefined && chartData[0]?.long === undefined && (
                <Line
                  yAxisId="right"
                  name={seriesNames?.leverage || "Leverage"}
                  type="monotone"
                  dataKey="leverage"
                  stroke="#39FF14"
                  strokeWidth={2}
                  dot={{ fill: '#39FF14', r: 4 }}
                  activeDot={{ r: 6, fill: '#39FF14', strokeWidth: 2, stroke: '#0a0e17' }}
                />
              )}
            </ComposedChart>
          ) : (
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3e" />
              <XAxis
                dataKey="name"
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              <YAxis
                stroke="#8E9297"
                style={{ fontSize: '12px', fontFamily: 'var(--font-mono)' }}
                tick={{ fill: '#8E9297' }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="value" name={seriesNames?.value || "Value"} fill={color + '88'} barSize={12} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>

      {/* Scan line effect */}
      <motion.div
        className="absolute left-0 w-full h-px bg-gradient-to-r from-transparent via-[#39FF14] to-transparent opacity-0 group-hover:opacity-100"
        animate={{
          y: [0, 300],
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "linear"
        }}
      />
    </motion.div>
  );
}