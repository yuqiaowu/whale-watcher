import { motion } from "motion/react";
import { useLanguage } from "@/app/i18n/LanguageContext";
import { useState } from "react";
import { DonationModal } from "@/app/components/donation-modal";

interface CyberHeaderProps {
  activePage: string;
  onPageChange: (page: string) => void;
}

export function CyberHeader({ activePage, onPageChange }: CyberHeaderProps) {
  const { t, toggleLanguage, language } = useLanguage();
  const [isDonationModalOpen, setIsDonationModalOpen] = useState(false);

  const handleNavClick = (item: string) => {
    if (item === t.nav.buyMeTea) {
      setIsDonationModalOpen(true);
    } else if (item === t.nav.liquidity) {
      onPageChange('liquidity');
    } else if (item === t.nav.aiCopyTrading) {
      onPageChange('aiTrading');
    }
  };

  return (
    <>
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="sticky top-0 z-50 backdrop-blur-sm bg-[#0A0C0E]/90 border-b border-[#2D3139]"
      >
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <motion.div
              className="flex items-center gap-2"
              whileHover={{ scale: 1.05 }}
            >
              <div
                className="text-xl font-mono font-bold text-[#39FF14] tracking-wider"
                style={{
                  textShadow: '0 0 10px rgba(57, 255, 20, 0.5)'
                }}
              >
                <span className="inline-block">{t.title}</span>
              </div>
              <div className="w-2 h-2 bg-[#39FF14] rounded-full animate-pulse shadow-[0_0_10px_rgba(57,255,20,0.8)]" />
            </motion.div>

            {/* Navigation */}
            <nav className="flex items-center gap-8">
              {[t.nav.liquidity, t.nav.aiCopyTrading, t.nav.buyMeTea].map((item, index) => {
                const isActive =
                  (item === t.nav.liquidity && activePage === 'liquidity') ||
                  (item === t.nav.aiCopyTrading && activePage === 'aiTrading');

                return (
                  <motion.button
                    key={index}
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.1 }}
                    whileHover={{
                      scale: 1.05,
                      textShadow: "0 0 8px rgba(57, 255, 20, 0.6)"
                    }}
                    className={`text-sm font-mono tracking-wide ${isActive
                      ? 'text-[#39FF14]'
                      : 'text-[#8E9297] hover:text-[#39FF14]'
                      } transition-colors relative group`}
                    style={isActive ? {
                      textShadow: '0 0 8px rgba(57, 255, 20, 0.4)'
                    } : undefined}
                    onClick={() => handleNavClick(item)}
                  >
                    {item}
                    <span className={`absolute bottom-0 left-0 h-0.5 bg-[#39FF14] transition-all duration-300 shadow-[0_0_5px_rgba(57,255,20,0.6)] ${isActive
                      ? 'w-full'
                      : 'w-0 group-hover:w-full'
                      }`} />
                  </motion.button>
                );
              })}

              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={toggleLanguage}
                className="px-4 py-1.5 text-sm font-mono bg-transparent border border-[#39FF14] text-[#39FF14] hover:bg-[#39FF1422] transition-colors shadow-[0_0_10px_rgba(57,255,20,0.3)] hover:shadow-[0_0_15px_rgba(57,255,20,0.5)]"
              >
                {language === 'zh' ? 'EN' : '中文'}
              </motion.button>
            </nav>
          </div>

          {/* Scan line effect */}
          <motion.div
            className="absolute top-0 left-0 w-full h-0.5 bg-gradient-to-r from-transparent via-[#39FF14] to-transparent opacity-50"
            animate={{
              x: ['-100%', '100%'],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "linear"
            }}
          />
        </div>
      </motion.header>
      <DonationModal isOpen={isDonationModalOpen} onClose={() => setIsDonationModalOpen(false)} />
    </>
  );
}