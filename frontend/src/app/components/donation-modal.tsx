import { motion, AnimatePresence } from "motion/react";
import { X, Copy, Check } from "lucide-react";
import { useState } from "react";
import { useLanguage } from "@/app/i18n/LanguageContext";

interface DonationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type PaymentMethod = 'SOL' | 'ALIPAY';

export function DonationModal({ isOpen, onClose }: DonationModalProps) {
  const { t } = useLanguage();
  const [copied, setCopied] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('SOL');

  const solWalletAddress = "2oAoK4D4hq5nGE2JVSknuWY4YDxaF5u7uB1arf1s2TNY";
  const alipayAccount = "newjowu@gmail.com";
  const solBlinkUrl = "https://www.dial.to/?action=solana-action:https://action.solscan.io/api/donate?receiver=2oAoK4D4hq5nGE2JVSknuWY4YDxaF5u7uB1arf1s2TNY";

  const currentAddress = paymentMethod === 'SOL' ? solWalletAddress : alipayAccount;

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(currentAddress);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handlePaymentMethodChange = (method: PaymentMethod) => {
    setPaymentMethod(method);
    setCopied(false);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md bg-[#1a1a1a] border border-[#2D3139] z-50 overflow-hidden"
            style={{
              boxShadow: '0 0 40px rgba(57, 255, 20, 0.2)'
            }}
          >
            {/* Header */}
            <div className="relative border-b border-[#2D3139] px-6 py-4 bg-[#14171a]">
              <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-[#39FF14] to-transparent opacity-50" />
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-mono font-bold text-[#39FF14] tracking-wide" style={{ textShadow: '0 0 8px rgba(57, 255, 20, 0.4)' }}>
                  {t.donation.title}
                </h2>
                <motion.button
                  whileHover={{ scale: 1.1, rotate: 90 }}
                  whileTap={{ scale: 0.9 }}
                  onClick={onClose}
                  className="text-[#8E9297] hover:text-[#39FF14] transition-colors"
                >
                  <X className="w-5 h-5" />
                </motion.button>
              </div>
              <p className="text-xs font-sans text-[#8E9297] mt-2">
                {t.donation.subtitle}
              </p>
            </div>

            {/* Content */}
            <div className="px-6 py-6 overflow-y-auto max-h-[80vh]">
              {/* Payment Method Selection */}
              <div className="mb-6">
                <label className="text-xs font-mono text-[#8E9297] mb-2 block">
                  {t.donation.paymentMethod}
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handlePaymentMethodChange('SOL')}
                    className={`px-4 py-2 border font-mono text-sm font-bold transition-all ${paymentMethod === 'SOL'
                      ? 'bg-[#39FF14] text-black border-[#39FF14]'
                      : 'bg-[#0a0a0a] text-[#39FF14] border-[#39FF14] hover:bg-[#39FF1422]'
                      }`}
                    style={
                      paymentMethod === 'SOL'
                        ? { boxShadow: '0 0 10px rgba(57, 255, 20, 0.4)' }
                        : undefined
                    }
                  >
                    SOL
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handlePaymentMethodChange('ALIPAY')}
                    className={`px-4 py-2 border font-mono text-sm font-bold transition-all ${paymentMethod === 'ALIPAY'
                      ? 'bg-[#39FF14] text-black border-[#39FF14]'
                      : 'bg-[#0a0a0a] text-[#39FF14] border-[#39FF14] hover:bg-[#39FF1422]'
                      }`}
                    style={
                      paymentMethod === 'ALIPAY'
                        ? { boxShadow: '0 0 10px rgba(57, 255, 20, 0.4)' }
                        : undefined
                    }
                  >
                    {t.donation.alipay}
                  </motion.button>
                </div>
              </div>

              {/* QR Code */}
              <div className="flex flex-col items-center mb-6">
                <div className="bg-white p-2 rounded-lg mb-4 overflow-hidden flex items-center justify-center w-[200px] h-[200px]">
                  <img
                    src={paymentMethod === 'SOL' ? "/sol_qr.png" : "/alipay_qr.png"}
                    alt="QR Code"
                    className="w-full h-full object-contain"
                  />
                </div>
                {paymentMethod === 'SOL' && (
                  <div className="flex flex-col items-center gap-1">
                    <div className="px-3 py-1 bg-[#39FF1422] border border-[#39FF14] rounded text-[10px] font-mono text-[#39FF14] animate-pulse">
                      {t.donation.stablecoinSupport}
                    </div>
                  </div>
                )}
              </div>

              <div className="text-center text-xs font-mono text-[#8E9297] mb-4">
                {paymentMethod === 'SOL' ? t.donation.scanQR : t.donation.scanAlipay}
              </div>

              {/* Solana Blink Option (Only for SOL) */}
              {paymentMethod === 'SOL' && (
                <div className="mb-6">
                  <label className="text-xs font-mono text-[#8E9297] mb-2 block">
                    {t.donation.solanaBlink}
                  </label>
                  <motion.a
                    href={solBlinkUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className="w-full py-3 bg-gradient-to-r from-[#14F195] to-[#9945FF] text-white font-mono text-xs font-bold flex items-center justify-center gap-2 rounded-sm"
                    style={{
                      boxShadow: '0 0 15px rgba(153, 69, 255, 0.4)'
                    }}
                  >
                    🚀 {t.donation.openBlink}
                  </motion.a>
                  <p className="text-[10px] text-[#8E9297] mt-2 text-center italic">
                    * {t.donation.solanaBlink}
                  </p>
                </div>
              )}

              {/* Wallet Address / Account */}
              <div className="mb-6">
                <label className="text-xs font-mono text-[#8E9297] mb-2 block">
                  {paymentMethod === 'SOL' ? t.donation.walletAddress : t.donation.alipayAccount}
                </label>
                <div className="flex gap-2">
                  <div className="flex-1 bg-[#0a0a0a] border border-[#2D3139] px-3 py-2 text-xs font-mono text-[#E8E8E8] overflow-x-auto whitespace-nowrap scrollbar-hide">
                    {currentAddress}
                  </div>
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={copyToClipboard}
                    className="px-4 py-2 bg-[#39FF14] text-black font-mono text-xs font-bold hover:bg-[#2DD00F] transition-colors flex items-center gap-2 shrink-0"
                    style={{
                      boxShadow: '0 0 10px rgba(57, 255, 20, 0.3)'
                    }}
                  >
                    {copied ? (
                      <>
                        <Check className="w-4 h-4" />
                        {t.donation.copied}
                      </>
                    ) : (
                      <>
                        <Copy className="w-4 h-4" />
                        {t.donation.copyAddress}
                      </>
                    )}
                  </motion.button>
                </div>
              </div>

              {/* Thank You Message */}
              <div className="text-center">
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                  className="text-sm font-sans text-[#39FF14] mb-4"
                  style={{ textShadow: '0 0 8px rgba(57, 255, 20, 0.3)' }}
                >
                  {t.donation.thankYou}
                </motion.div>
              </div>
            </div>

            {/* Footer Decoration */}
            <div className="relative h-1 bg-gradient-to-r from-transparent via-[#39FF14] to-transparent opacity-50" />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}