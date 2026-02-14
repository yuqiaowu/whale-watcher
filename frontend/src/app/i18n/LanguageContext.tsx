import { createContext, useContext, useState, ReactNode } from 'react';
import { translations, Language } from './translations';

interface LanguageContextType {
  language: Language;
  toggleLanguage: () => void;
  t: typeof translations.zh;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const detectSystemLanguage = (): Language => {
    if (typeof navigator !== 'undefined') {
      const lang = navigator.language.toLowerCase();
      if (lang.startsWith('en')) return 'en';
    }
    return 'zh';
  };

  const [language, setLanguage] = useState<Language>(detectSystemLanguage);

  const toggleLanguage = () => {
    setLanguage(prev => prev === 'zh' ? 'en' : 'zh');
  };

  const value = {
    language,
    toggleLanguage,
    t: translations[language]
  };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    // During hot module reload, return default values to prevent crashes
    if (import.meta.hot) {
      return {
        language: 'zh' as Language,
        toggleLanguage: () => { },
        t: translations.zh
      };
    }
    throw new Error('useLanguage must be used within LanguageProvider');
  }
  return context;
}