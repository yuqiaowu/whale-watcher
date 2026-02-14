import { motion } from "motion/react";
import { useLanguage } from "@/app/i18n/LanguageContext";

export function LiveIndicator() {
  const { t } = useLanguage();
  
  return (
    <div className="flex items-center gap-4 mb-8">
      <div className="flex items-center gap-2">
        <motion.div
          animate={{
            scale: [1, 1.2, 1],
            opacity: [1, 0.5, 1],
          }}
          transition={{
            duration: 1.5,
            repeat: Infinity,
            ease: "easeInOut"
          }}
          className="w-3 h-3 bg-[#39FF14] rounded-full"
          style={{ boxShadow: '0 0 10px rgba(57, 255, 20, 0.8)' }}
        />
        <span className="text-[#39FF14] font-mono text-sm tracking-wide" style={{ textShadow: '0 0 8px rgba(57, 255, 20, 0.4)' }}>{t.live.dataStream}</span>
      </div>

      <div className="flex-1 h-px bg-gradient-to-r from-[#39FF1444] to-transparent" />

      <div className="font-mono text-xs text-[#8E9297]">
        <motion.span
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          {t.live.lastUpdate}: {new Date().toLocaleTimeString('zh-CN')}
        </motion.span>
      </div>
    </div>
  );
}