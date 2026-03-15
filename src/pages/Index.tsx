import { useState } from "react";
import Icon from "@/components/ui/icon";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyIcon = any;

const NAV_ITEMS = [
  { id: "constructor", label: "Конструктор", icon: "Layers" },
  { id: "templates", label: "Шаблоны", icon: "LayoutGrid" },
  { id: "cabinet", label: "Мой кабинет", icon: "User" },
  { id: "marketplace", label: "Маркетплейс", icon: "ShoppingBag" },
  { id: "docs", label: "Документация", icon: "BookOpen" },
  { id: "support", label: "Поддержка", icon: "Headphones" },
  { id: "gallery", label: "Галерея", icon: "Image" },
];

const TEMPLATES = [
  { name: "Фитнес-трекер", category: "Здоровье", color: "from-violet-500 to-blue-500", icon: "Activity", downloads: "12.4K" },
  { name: "Доставка еды", category: "E-commerce", color: "from-pink-500 to-orange-400", icon: "ShoppingCart", downloads: "9.8K" },
  { name: "Финансы", category: "Банкинг", color: "from-cyan-500 to-blue-600", icon: "TrendingUp", downloads: "15.1K" },
  { name: "Медитация", category: "Велнес", color: "from-purple-500 to-pink-500", icon: "Heart", downloads: "7.3K" },
  { name: "Обучение", category: "EdTech", color: "from-green-400 to-cyan-500", icon: "GraduationCap", downloads: "11.2K" },
  { name: "Маркетплейс", category: "E-commerce", color: "from-orange-400 to-red-500", icon: "Store", downloads: "8.7K" },
];

const MONETIZATION = [
  {
    icon: "Crown",
    title: "Подписки",
    desc: "Ежемесячные и годовые планы с автоматическим продлением через App Store",
    color: "from-violet-500 to-purple-600",
    features: ["Free Trial", "Семейная подписка", "Промокоды"],
  },
  {
    icon: "Package",
    title: "Внутренние покупки",
    desc: "Расходуемые и постоянные покупки в приложении с безопасными транзакциями",
    color: "from-blue-500 to-cyan-500",
    features: ["Виртуальная валюта", "Разблокировка уровней", "Премиум-контент"],
  },
  {
    icon: "Radio",
    title: "Реклама",
    desc: "Интеграция AdMob, Unity Ads и AppLovin для монетизации через рекламу",
    color: "from-pink-500 to-rose-600",
    features: ["Баннеры", "Interstitial", "Reward-видео"],
  },
];

const FEATURES = [
  { icon: "Cpu", title: "ИИ-помощник", desc: "Генерирует код, экраны и логику по описанию на русском языке" },
  { icon: "Zap", title: "Drag & Drop", desc: "Визуальный редактор с готовыми компонентами iOS" },
  { icon: "GitBranch", title: "Нативный код", desc: "Экспорт в Swift, SwiftUI и Xcode-проект" },
  { icon: "Globe", title: "Публикация", desc: "Автоматическая отправка в App Store в один клик" },
  { icon: "Shield", title: "Безопасность", desc: "Шифрование данных и соответствие требованиям Apple" },
  { icon: "BarChart2", title: "Аналитика", desc: "Встроенная аналитика поведения пользователей" },
];

const STATS = [
  { num: "50K+", label: "Разработчиков" },
  { num: "12K+", label: "Опубликованных приложений" },
  { num: "98%", label: "Одобрение App Store" },
  { num: "4.9★", label: "Рейтинг платформы" },
];

const GALLERY = [
  { name: "SportApp", category: "Спорт", color: "from-green-400 to-teal-500", screens: 8 },
  { name: "TravelGo", category: "Путешествия", color: "from-blue-400 to-indigo-600", screens: 12 },
  { name: "ChefPro", category: "Рецепты", color: "from-orange-400 to-red-500", screens: 6 },
  { name: "MindSpace", category: "Медитация", color: "from-purple-400 to-pink-500", screens: 10 },
];

export default function Index() {
  const [activeSection, setActiveSection] = useState("constructor");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [activePlan, setActivePlan] = useState(1);

  return (
    <div className="min-h-screen bg-background text-foreground overflow-x-hidden">
      {/* Animated mesh background */}
      <div className="mesh-bg">
        <div className="mesh-orb" />
        <div className="mesh-orb" />
        <div className="mesh-orb" />
        <div className="mesh-orb" />
      </div>

      {/* NAVBAR */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/5 bg-background/70 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 flex items-center justify-between h-16">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl btn-gradient flex items-center justify-center shadow-lg shadow-violet-500/30">
              <span className="relative z-10 text-white text-sm">⚡</span>
            </div>
            <span className="font-heading font-black text-lg tracking-tight">
              <span className="gradient-text">App</span>
              <span className="text-white font-bold">Forge</span>
            </span>
          </div>

          <div className="hidden lg:flex items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id)}
                className={`px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 flex items-center gap-2 ${
                  activeSection === item.id
                    ? "bg-white/8 text-white"
                    : "text-muted-foreground hover:text-white hover:bg-white/5"
                }`}
              >
                <Icon name={item.icon as AnyIcon} size={14} />
                <span className={activeSection === item.id ? "nav-active" : ""}>{item.label}</span>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3">
            <button className="hidden sm:block text-sm text-muted-foreground hover:text-white transition-colors px-4 py-2">
              Войти
            </button>
            <button className="btn-gradient text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-lg shadow-violet-500/30">
              <span>Начать бесплатно</span>
            </button>
            <button className="lg:hidden text-muted-foreground" onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
              <Icon name={mobileMenuOpen ? "X" : "Menu"} size={20} />
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <div className="lg:hidden border-t border-white/5 bg-background/95 backdrop-blur-xl px-6 py-4 flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => { setActiveSection(item.id); setMobileMenuOpen(false); }}
                className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-muted-foreground hover:text-white hover:bg-white/5 transition-all text-left"
              >
                <Icon name={item.icon as AnyIcon} size={16} />
                {item.label}
              </button>
            ))}
          </div>
        )}
      </nav>

      {/* HERO */}
      <section className="relative pt-32 pb-20 px-6">
        <div className="max-w-6xl mx-auto relative z-10">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 tag-badge mb-6 animate-fade-up">
              ✦ Платформа нового поколения
            </div>

            <h1 className="font-heading font-black text-5xl md:text-7xl lg:text-8xl leading-tight tracking-tighter mb-6 animate-fade-up delay-100">
              <span className="text-white">Создавай</span>{" "}
              <span className="gradient-text">iOS-приложения</span>
              <br />
              <span className="text-white">без кода</span>
            </h1>

            <p className="text-muted-foreground text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed animate-fade-up delay-200">
              Конструктор + шаблоны + ИИ. Опиши идею на русском —
              получи готовое приложение для App Store за часы, а не месяцы.
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 animate-fade-up delay-300">
              <button className="btn-gradient text-white font-bold text-base px-8 py-4 rounded-2xl shadow-2xl shadow-violet-500/40 w-full sm:w-auto">
                <span className="flex items-center gap-2">
                  <Icon name="Rocket" size={18} />
                  Начать бесплатно
                </span>
              </button>
              <button className="glass-card text-white font-semibold text-base px-8 py-4 rounded-2xl w-full sm:w-auto flex items-center justify-center gap-2 glow-hover">
                <Icon name="Play" size={16} className="text-violet-400" />
                Смотреть демо
              </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 max-w-3xl mx-auto animate-fade-up delay-400">
              {STATS.map((s) => (
                <div key={s.label} className="glass-card rounded-2xl p-4 glow-hover">
                  <div className="font-heading font-black text-2xl md:text-3xl gradient-text stat-num">{s.num}</div>
                  <div className="text-muted-foreground text-xs mt-1">{s.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* iPhone mockups */}
          <div className="mt-20 flex items-end justify-center gap-4 md:gap-6 animate-fade-up delay-500">
            {[
              { color: "from-violet-600 to-blue-500", scale: "scale-90 opacity-60", content: "🎵" },
              { color: "from-pink-500 to-violet-600", scale: "scale-100", content: "🏃" },
              { color: "from-cyan-500 to-blue-500", scale: "scale-90 opacity-60", content: "💰" },
            ].map((phone, i) => (
              <div key={i} className={`relative ${phone.scale} transition-all duration-500`}>
                <div className="w-32 md:w-40 h-64 md:h-80 glass-card rounded-[2.5rem] border border-white/10 overflow-hidden shimmer">
                  <div className={`absolute inset-0 bg-gradient-to-br ${phone.color} opacity-20`} />
                  <div className="absolute top-3 left-1/2 -translate-x-1/2 w-16 h-5 bg-black/80 rounded-full" />
                  <div className="flex items-center justify-center h-full text-4xl">{phone.content}</div>
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 w-20 h-1 bg-white/30 rounded-full" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="relative py-20 px-6">
        <div className="max-w-6xl mx-auto relative z-10">
          <div className="text-center mb-14">
            <div className="tag-badge inline-block mb-4">Возможности</div>
            <h2 className="font-heading font-black text-4xl md:text-5xl text-white mb-4">
              Всё необходимое<br />
              <span className="gradient-text">в одном месте</span>
            </h2>
            <p className="text-muted-foreground max-w-xl mx-auto">
              От идеи до публикации в App Store — полный цикл разработки iOS-приложений
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f, i) => (
              <div
                key={f.title}
                className="glass-card rounded-2xl p-6 card-lift glow-hover"
                style={{ animationDelay: `${i * 0.08}s` }}
              >
                <div className="w-12 h-12 rounded-2xl btn-gradient flex items-center justify-center mb-4 shadow-lg shadow-violet-500/30">
                  <span className="relative z-10">
                    <Icon name={f.icon as AnyIcon} size={20} className="text-white" />
                  </span>
                </div>
                <h3 className="font-heading font-bold text-lg text-white mb-2">{f.title}</h3>
                <p className="text-muted-foreground text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TEMPLATES */}
      <section className="relative py-20 px-6">
        <div className="max-w-6xl mx-auto relative z-10">
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-12 gap-4">
            <div>
              <div className="tag-badge inline-block mb-4">Шаблоны</div>
              <h2 className="font-heading font-black text-4xl md:text-5xl text-white">
                Готовые шаблоны<br />
                <span className="gradient-text-alt">для старта</span>
              </h2>
            </div>
            <button className="glass-card px-6 py-3 rounded-2xl text-sm font-semibold text-white glow-hover flex items-center gap-2 self-start md:self-auto">
              Все шаблоны <Icon name="ArrowRight" size={16} />
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {TEMPLATES.map((t, i) => (
              <div
                key={t.name}
                className="glass-card rounded-2xl overflow-hidden card-lift glow-hover cursor-pointer group"
                style={{ animationDelay: `${i * 0.1}s` }}
              >
                <div className={`h-40 bg-gradient-to-br ${t.color} relative`}>
                  <div className="absolute inset-0 flex items-center justify-center opacity-30">
                    <Icon name={t.icon as AnyIcon} size={64} className="text-white" />
                  </div>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Icon name={t.icon as AnyIcon} size={36} className="text-white drop-shadow-lg" />
                  </div>
                  <div className="absolute top-3 right-3 bg-black/30 backdrop-blur-sm text-white text-xs px-3 py-1 rounded-full">
                    {t.downloads} скачиваний
                  </div>
                </div>
                <div className="p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="font-heading font-bold text-white">{t.name}</h3>
                      <p className="text-muted-foreground text-xs mt-1">{t.category}</p>
                    </div>
                    <button className="btn-gradient w-9 h-9 rounded-xl flex items-center justify-center shadow-md shadow-violet-500/30 opacity-0 group-hover:opacity-100 transition-opacity">
                      <span className="relative z-10"><Icon name="Plus" size={16} className="text-white" /></span>
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* MONETIZATION */}
      <section className="relative py-20 px-6">
        <div className="max-w-6xl mx-auto relative z-10">
          <div className="text-center mb-14">
            <div className="tag-badge inline-block mb-4">Монетизация</div>
            <h2 className="font-heading font-black text-4xl md:text-5xl text-white mb-4">
              Зарабатывай<br />
              <span className="gradient-text">с первого дня</span>
            </h2>
            <p className="text-muted-foreground max-w-xl mx-auto">
              Встроенные инструменты монетизации — настройте один раз и получайте доход
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {MONETIZATION.map((m) => (
              <div key={m.title} className="glass-card rounded-3xl p-7 card-lift glow-hover relative overflow-hidden">
                <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${m.color} opacity-10 rounded-full blur-2xl`} />
                <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${m.color} flex items-center justify-center mb-5 shadow-lg`}>
                  <Icon name={m.icon as AnyIcon} size={24} className="text-white" />
                </div>
                <h3 className="font-heading font-bold text-xl text-white mb-3">{m.title}</h3>
                <p className="text-muted-foreground text-sm mb-5 leading-relaxed">{m.desc}</p>
                <div className="space-y-2">
                  {m.features.map((f) => (
                    <div key={f} className="flex items-center gap-2 text-sm text-foreground/80">
                      <div className={`w-5 h-5 rounded-full bg-gradient-to-br ${m.color} flex items-center justify-center flex-shrink-0`}>
                        <Icon name="Check" size={11} className="text-white" />
                      </div>
                      {f}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section className="relative py-20 px-6">
        <div className="max-w-5xl mx-auto relative z-10">
          <div className="text-center mb-14">
            <div className="tag-badge inline-block mb-4">Тарифы</div>
            <h2 className="font-heading font-black text-4xl md:text-5xl text-white mb-4">
              Простые цены<br />
              <span className="gradient-text">без сюрпризов</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                name: "Старт",
                price: "0",
                period: "бесплатно",
                desc: "Для знакомства с платформой",
                features: ["1 приложение", "5 шаблонов", "Базовый конструктор", "Экспорт в Xcode"],
                cta: "Начать бесплатно",
                highlight: false,
              },
              {
                name: "Про",
                price: "2 990",
                period: "₽ / мес",
                desc: "Для серьёзных проектов",
                features: ["10 приложений", "Все шаблоны", "ИИ-помощник", "Монетизация", "Приоритетная поддержка"],
                cta: "Попробовать 14 дней",
                highlight: true,
              },
              {
                name: "Бизнес",
                price: "9 990",
                period: "₽ / мес",
                desc: "Для команд и агентств",
                features: ["Безлимит приложений", "Белый лейбл", "API-интеграции", "Выделенный менеджер", "SLA 99.9%"],
                cta: "Связаться с нами",
                highlight: false,
              },
            ].map((plan, i) => (
              <div
                key={plan.name}
                onClick={() => setActivePlan(i)}
                className={`relative rounded-3xl p-7 cursor-pointer transition-all duration-300 ${
                  plan.highlight
                    ? "bg-gradient-to-br from-violet-600/20 to-blue-600/20 border-2 border-violet-500/50 shadow-2xl shadow-violet-500/20"
                    : "glass-card glow-hover"
                } ${activePlan === i ? "scale-105" : ""}`}
              >
                {plan.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 tag-badge bg-gradient-to-r from-violet-500 to-blue-500 text-white border-0 whitespace-nowrap">
                    Популярный
                  </div>
                )}
                <div className="mb-5">
                  <h3 className="font-heading font-bold text-lg text-white mb-1">{plan.name}</h3>
                  <p className="text-muted-foreground text-xs">{plan.desc}</p>
                </div>
                <div className="mb-6">
                  <span className="font-heading font-black text-4xl text-white">{plan.price}</span>
                  <span className="text-muted-foreground text-sm ml-1">{plan.period}</span>
                </div>
                <div className="space-y-3 mb-7">
                  {plan.features.map((f) => (
                    <div key={f} className="flex items-center gap-2 text-sm text-foreground/80">
                      <Icon name="Check" size={14} className="text-violet-400 flex-shrink-0" />
                      {f}
                    </div>
                  ))}
                </div>
                <button
                  className={`w-full py-3 rounded-2xl font-semibold text-sm transition-all ${
                    plan.highlight
                      ? "btn-gradient text-white shadow-lg shadow-violet-500/30"
                      : "glass-card text-white hover:bg-white/8"
                  }`}
                >
                  <span className="relative z-10">{plan.cta}</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* GALLERY */}
      <section className="relative py-20 px-6">
        <div className="max-w-6xl mx-auto relative z-10">
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-12 gap-4">
            <div>
              <div className="tag-badge inline-block mb-4">Галерея</div>
              <h2 className="font-heading font-black text-4xl md:text-5xl text-white">
                Примеры<br />
                <span className="gradient-text">реальных проектов</span>
              </h2>
            </div>
            <button className="glass-card px-6 py-3 rounded-2xl text-sm font-semibold text-white glow-hover flex items-center gap-2 self-start md:self-auto">
              Открыть галерею <Icon name="ArrowRight" size={16} />
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {GALLERY.map((g) => (
              <div key={g.name} className="glass-card rounded-2xl overflow-hidden card-lift glow-hover group cursor-pointer">
                <div className={`h-48 bg-gradient-to-br ${g.color} relative flex items-end p-4`}>
                  <div className="absolute inset-0 opacity-20 flex items-center justify-center text-7xl font-black text-white font-heading">
                    {g.name[0]}
                  </div>
                  <div className="relative z-10 bg-black/40 backdrop-blur-sm rounded-xl px-3 py-1.5 text-xs text-white font-medium">
                    {g.screens} экранов
                  </div>
                </div>
                <div className="p-4">
                  <h3 className="font-heading font-bold text-white text-sm">{g.name}</h3>
                  <p className="text-muted-foreground text-xs mt-0.5">{g.category}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA BANNER */}
      <section className="relative py-20 px-6">
        <div className="max-w-4xl mx-auto relative z-10">
          <div className="relative rounded-3xl overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-violet-600/30 via-blue-600/20 to-pink-600/30" />
            <div className="absolute inset-0 border border-white/10 rounded-3xl" />
            <div className="relative z-10 p-10 md:p-16 text-center">
              <h2 className="font-heading font-black text-4xl md:text-5xl text-white mb-4">
                Готов создать<br />
                <span className="gradient-text">своё приложение?</span>
              </h2>
              <p className="text-muted-foreground text-lg mb-8 max-w-xl mx-auto">
                Присоединяйся к 50,000+ разработчикам, которые уже создают iOS-приложения с AppForge
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <button className="btn-gradient text-white font-bold text-base px-8 py-4 rounded-2xl shadow-2xl shadow-violet-500/40 w-full sm:w-auto">
                  <span className="flex items-center justify-center gap-2">
                    <Icon name="Rocket" size={18} />
                    Начать бесплатно
                  </span>
                </button>
                <button className="glass-card text-white font-semibold px-8 py-4 rounded-2xl w-full sm:w-auto text-base glow-hover">
                  Записаться на демо
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="relative border-t border-white/5 py-12 px-6">
        <div className="max-w-6xl mx-auto relative z-10">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-8 mb-10">
            <div className="md:col-span-2">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-xl btn-gradient flex items-center justify-center">
                  <span className="relative z-10 text-white text-sm">⚡</span>
                </div>
                <span className="font-heading font-black text-lg">
                  <span className="gradient-text">App</span>
                  <span className="text-white">Forge</span>
                </span>
              </div>
              <p className="text-muted-foreground text-sm leading-relaxed max-w-xs">
                Платформа для создания iOS-приложений без написания кода. Конструктор, шаблоны и ИИ.
              </p>
            </div>
            {[
              { title: "Продукт", links: ["Конструктор", "Шаблоны", "Маркетплейс", "Галерея"] },
              { title: "Компания", links: ["О нас", "Блог", "Карьера", "Пресса"] },
              { title: "Поддержка", links: ["Документация", "Сообщество", "Статус", "Контакты"] },
            ].map((col) => (
              <div key={col.title}>
                <h4 className="font-heading font-bold text-sm text-white mb-4">{col.title}</h4>
                <ul className="space-y-2">
                  {col.links.map((l) => (
                    <li key={l}>
                      <a href="#" className="text-muted-foreground text-sm hover:text-white transition-colors">
                        {l}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="border-t border-white/5 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
            <p className="text-muted-foreground text-xs">© 2026 AppForge. Все права защищены.</p>
            <div className="flex items-center gap-4">
              {["Telegram", "Twitter", "Youtube"].map((s) => (
                <button key={s} className="text-muted-foreground hover:text-white text-xs transition-colors">{s}</button>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}