import { createContext, useContext, useState, ReactNode } from 'react';
import { translations, Language } from './translations';

interface LanguageContextType {
  language: Language;
  setLanguage: (language: Language) => void;
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

  const getInitialLanguage = (): Language => {
    if (typeof window !== 'undefined') {
      const saved = window.localStorage.getItem('preferred-language');
      if (saved === 'zh' || saved === 'en') return saved;
    }
    return detectSystemLanguage();
  };

  const [language, setLanguageState] = useState<Language>(getInitialLanguage);

  const setLanguage = (nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('preferred-language', nextLanguage);
      document.documentElement.lang = nextLanguage === 'zh' ? 'zh-CN' : 'en';
    }
  };

  const toggleLanguage = () => {
    setLanguage(language === 'zh' ? 'en' : 'zh');
  };

  const value = {
    language,
    setLanguage,
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
        setLanguage: () => { },
        toggleLanguage: () => { },
        t: translations.zh
      };
    }
    throw new Error('useLanguage must be used within LanguageProvider');
  }
  return context;
}
