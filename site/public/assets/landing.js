(function () {
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var root = document.documentElement;
  root.classList.add("js");

  /* ---------- Traduções. O português fica no próprio HTML; aqui vão inglês e espanhol. ---------- */
  var I18N = {
    "en-US": {
      "aria.nav": "Main", "aria.rows": "Sample exceptions queue", "aria.marquee": "Who it is for", "aria.prev": "Previous step", "aria.next": "Next step", "aria.orbit": "Collection steps",
      "nav.product": "Product", "nav.ruler": "Cadence", "nav.recon": "Reconciliation", "nav.price": "Pricing", "nav.cta": "Join the pilot", "nav.login": "Sign in", "ft.login": "Client area", "wa.float": "Talk to us", "aria.wa": "Chat with Kitou on WhatsApp",
      "hero.badgeB": "Pilot open", "hero.badge": "For SMBs billing via PIX and boleto",
      "hero.h1a": "Collect on WhatsApp.", "hero.h1b": "Settle from the",
      "hero.lede": "Kitou sends reminders, negotiates and receives payment receipts on WhatsApp. Every bank entry is checked against the right invoice, and a receipt alone never settles anything.",
      "hero.cta1": "Join the pilot", "hero.cta2": "See reconciliation", "hero.note": "Asaas · Inter · Open Finance · official Meta templates",
      "app.home": "Home", "app.exc": "Exceptions", "app.pay": "Payments", "app.inv": "Invoices", "app.conv": "Conversations", "app.deliv": "Deliveries", "app.appr": "Approvals", "app.metrics": "Metrics", "app.settings": "Settings",
      "app.title": "Clínica Demo · November", "app.sample": "Sample data",
      "app.k1": "Auto-settled", "app.k2": "Recovery", "app.k3": "Days late", "app.k4": "Open exceptions",
      "app.h1": "TYPE", "app.h2": "PAYER", "app.h3": "INVOICE", "app.h4": "AMOUNT",
      "app.t1": "suggestion", "app.t2": "mismatch", "app.t3": "unidentified", "app.t4": "reconciled",
      "app.inv1": "Nov tuition", "app.inv2": "Installment 2/6", "app.inv3": "no match",
      "app.a1": "Confirm", "app.a2": "Apply partial", "app.a3": "Search", "app.a4": "layer 1",
      "m.1": "Clinics", "m.2": "Schools", "m.3": "Gyms", "m.4": "Condos", "m.5": "Subscriptions", "m.6": "Recurring B2B", "m.7": "Finance BPOs", "m.8": "Banks",
      "p.kicker": "Product", "p.h2": "Debtors chat. <span class=\"grad-text\">Your team only decides.</span>", "p.lede": "The cadence reminds, the agent replies and the dashboard shows only what the system could not close on its own.",
      "p.a.l": "WHATSAPP AGENT", "p.a.h": "Replies to what people write or say.", "p.a.p": "It takes the receipt, logs the promise and pauses the cadence. Disputes go straight to a person.",
      "p.a.m1": "\"I can only pay on the 25th, is that OK?\"", "p.a.s1": "voice note transcribed · 7:12 PM", "p.a.m2": "Got it, Marina. I noted your payment for Nov 25 and won't send reminders until then.", "p.a.s2": "agent · 7:12 PM",
      "p.b.l": "POLICY IS THE CEILING", "p.b.h": "The agent only offers what fits.", "p.b.o1": "Upfront, 10% off", "p.b.o2": "6 installments with down payment", "p.b.o3": "approval",
      "p.c.l": "RECEIPT ≠ SETTLEMENT", "p.c.h": "Only the bank settles an invoice.", "p.c.p": "The receipt waits until the bank statement or the issuer's webhook confirms it.", "p.c.t1": "waiting for bank",
      "p.d.l": "DEFAULT POLICY", "p.d.h": "You adjust it in Settings.", "p.d.1": "Upfront discount", "p.d.1v": "up to 10%", "p.d.2": "Minimum down payment", "p.d.3": "Installments", "p.d.3v": "up to 6", "p.d.4": "Promise", "p.d.4v": "up to 15 days",
      "p.e.l": "ONE ACCOUNT PER COMPANY", "p.e.h": "No data crosses over.", "p.e.p": "For a BPO, each client is an isolated account in the database.", "p.e.1": "Clinic", "p.e.2": "School", "p.e.3": "Gym",
      "r.kicker": "Default cadence", "r.h2": "Ten steps around every invoice.", "r.lede": "The cadence runs on a schedule, with no AI. Tap a step to see what goes out.",
      "r.h1": "Nothing goes out outside business hours. The default is 8 AM to 8 PM, Monday to Saturday.", "r.h2b": "Asked to stop, the cadence stops right away.", "r.h3": "No threats, no contacting third parties and no collecting in groups.",
      "r.core1": "invoice", "r.core2": "due",
      "c.kicker": "Reconciliation", "c.h2": "Every payment that comes in finds its invoice.", "c.lede": "The statement arrives on its own, through Open Finance or the issuer. The matcher stops at the first rule that fits, and nothing settles twice.",
      "c.feed": "statement · business account", "c.live": "live", "c.auto": "settled", "c.layer": "layer", "c.sugg": "suggestion", "c.queue": "queue", "c.e3": "similar name, 2 invoices", "c.e4": "no identifier", "c.boleto": "Boleto", "c.e5": "bank reference",
      "c.l1h": "Matching txid or E2E", "c.l1p": "Settled automatically.", "c.l2h": "Amount, tax ID and date", "c.l2p": "Settled automatically, from 10 days before to 60 days after the due date.", "c.l3h": "Amount, similar name and date", "c.l3p": "Scored suggestion for someone to confirm.", "c.l4h": "No candidate", "c.l4p": "Goes to the queue with everything the bank sent.",
      "g.kicker": "What the code won't negotiate", "g.h2": "AI does the talking. Money stays with the code and your team.",
      "g.1h": "AI doesn't decide money.", "g.1p": "It reads the receipt, transcribes the voice note and chats. The cadence, matching and settlement are fixed rules.",
      "g.2h": "The bank confirms settlement.", "g.2p": "A receipt alone never settles an invoice. Confirming without the bank is refused.",
      "g.3h": "Your policy is the ceiling.", "g.3p": "A request for 8 installments when the cap is 6 pauses the agent and opens an approval in the dashboard.",
      "g.4h": "A person has the final word.", "g.4p": "Uncertain matches, disputes, weak reads and invoices at D+30 go to the queue, and the owner is notified.",
      "g.5h": "Collections without embarrassment.", "g.5p": "Versioned messages that follow Brazil's Consumer Code (CDC, art. 42). Identity is confirmed before any amount is shown.",
      "pr.kicker": "Pricing", "pr.h2": "Start with reconciliation.", "pr.lede": "Checking what you receive already pays for itself. The WhatsApp cadence comes in whenever you want.",
      "pr.phase": "Phase 1 · Reconciliation", "pr.fee": "Monthly fee by tier", "pr.setup": "+ one-time setup", "pr.p": "Checks every PIX and boleto against the right invoice, without contacting the debtor. It's the entry point.",
      "pr.t1": "up to 300 invoices/mo", "pr.t2": "up to 1,500", "pr.t3": "up to 5,000",
      "pr.1": "Reconciliation of every payment that comes in, at any bank", "pr.2": "Period file ready for your accountant", "pr.3": "Exceptions queue for whatever the system couldn't close on its own", "pr.4": "Issuer setup and invoice import", "pr.cta1": "Start with reconciliation",
      "pr.b.phase": "Collections + reconciliation", "pr.b.fee": "Monthly fee by tier", "pr.b.var": "+ % of recovered overdue only", "pr.b.p": "The variable fee applies only to what was overdue and the bank confirmed. If nothing is recovered, you pay only the tier.",
      "pr.b.1": "Everything in reconciliation", "pr.b.2": "WhatsApp cadence with official templates; reminders before the due date are included in the monthly fee", "pr.b.3": "An agent that negotiates only within your policy", "pr.b.4": "Recovery measured against the baseline taken at onboarding", "pr.b.5": "Monthly cap on the variable fee: no surprise bills",
      "pr.cta": "Talk about the pilot", "pr.note": "Each tier's price is agreed in a call, based on portfolio size. In the pilot, the setup fee is waived in exchange for a case study.",
      "f.6q": "What counts as recovered?", "f.6a": "An invoice paid after its due date, with the settlement confirmed by the bank. Reminders before the due date and receipts without a bank statement don't count. The effect is measured against the onboarding baseline, and the variable fee has a monthly cap.",
      "f.1q": "Does my bank need an integration?", "f.1a": "No. The statement comes in through Open Finance from any account. Asaas and Inter already have issuer adapters. OFX and CSV are for exceptions only.",
      "f.2q": "What if a debtor sends a fake receipt?", "f.2a": "A receipt never settles. It waits for the bank and only becomes a settlement when the statement or webhook confirms the E2E ID, amount and date.",
      "f.3q": "Can the agent make up a discount?", "f.3a": "No. The options are generated by code from your policy. The agent only picks among them. Anything outside goes to approval.",
      "f.4q": "Could my number get banned?", "f.4a": "The cadence only uses Meta-approved templates, with send limits and instant opt-out. The account won't even turn on without a paired number and approved templates.",
      "f.5q": "I already use Pix Automático. Does this still help?", "f.5a": "Yes. When the automatic debit pays, D-3 and D0 drop out of the cadence. Kitou invites people to enroll and alerts you when a debit fails, on top of reconciling what comes in.",
      "cta.kicker": "Pilot", "cta.h2": "One portfolio, our team running it and results measured against how late you get paid today.", "cta.p": "The account starts switched off and only turns on when everything is in place. No debtor gets a message too early.",
      "cta.1": "Policy", "cta.2": "Cadence and hours", "cta.3": "Paired WhatsApp", "cta.4": "Approved templates", "cta.5": "Legal basis", "cta.b1": "Chat on WhatsApp", "cta.b2": "I'm already a client",
      "ft.c1": "PRODUCT", "ft.c2": "COMPANY", "ft.agent": "Agent", "ft.rules": "Rules", "ft.b1": "Collections and reconciliation on WhatsApp", "ft.b2": "PIX · boleto · Open Finance"
    },
    "es": {
      "aria.nav": "Principal", "aria.rows": "Cola de excepciones de ejemplo", "aria.marquee": "Para quién es", "aria.prev": "Etapa anterior", "aria.next": "Etapa siguiente", "aria.orbit": "Etapas de la cobranza",
      "nav.product": "Producto", "nav.ruler": "Secuencia", "nav.recon": "Conciliación", "nav.price": "Precio", "nav.cta": "Quiero el piloto", "nav.login": "Entrar", "ft.login": "Área del cliente", "wa.float": "Habla con nosotros", "aria.wa": "Hablar con Kitou por WhatsApp",
      "hero.badgeB": "Piloto abierto", "hero.badge": "Para pymes que cobran con PIX y boleto",
      "hero.h1a": "Cobra por WhatsApp.", "hero.h1b": "Concilia con el",
      "hero.lede": "Kitou recuerda, negocia y recibe el comprobante por WhatsApp. Cada ingreso del banco se cruza con la factura correcta, y un comprobante por sí solo nunca salda nada.",
      "hero.cta1": "Quiero el piloto", "hero.cta2": "Ver la conciliación", "hero.note": "Asaas · Inter · Open Finance · plantillas oficiales de Meta",
      "app.home": "Inicio", "app.exc": "Excepciones", "app.pay": "Pagos", "app.inv": "Facturas", "app.conv": "Conversaciones", "app.deliv": "Entregas", "app.appr": "Aprobaciones", "app.metrics": "Métricas", "app.settings": "Configuración",
      "app.title": "Clínica Demo · noviembre", "app.sample": "Datos de ejemplo",
      "app.k1": "Conciliación automática", "app.k2": "Recuperación", "app.k3": "Días de atraso", "app.k4": "Excepciones abiertas",
      "app.h1": "TIPO", "app.h2": "PAGADOR", "app.h3": "FACTURA", "app.h4": "MONTO",
      "app.t1": "sugerencia", "app.t2": "diferencia", "app.t3": "no identificado", "app.t4": "conciliado",
      "app.inv1": "Mensualidad nov", "app.inv2": "Cuota 2/6", "app.inv3": "sin candidato",
      "app.a1": "Confirmar", "app.a2": "Aplicar parcial", "app.a3": "Buscar", "app.a4": "capa 1",
      "m.1": "Clínicas", "m.2": "Escuelas", "m.3": "Gimnasios", "m.4": "Condominios", "m.5": "Suscripciones", "m.6": "B2B recurrente", "m.7": "BPO financiero", "m.8": "Bancos",
      "p.kicker": "Producto", "p.h2": "El deudor conversa. <span class=\"grad-text\">Tu equipo solo decide.</span>", "p.lede": "La secuencia recuerda, el agente responde y el panel muestra solo lo que el sistema no cerró por sí mismo.",
      "p.a.l": "AGENTE DE WHATSAPP", "p.a.h": "Responde lo que la persona escribió o dijo.", "p.a.p": "Recibe el comprobante, registra la promesa y pausa la secuencia. Una disputa pasa directo a una persona.",
      "p.a.m1": "\"Solo puedo pagar el día 25, ¿está bien?\"", "p.a.s1": "audio transcrito · 19:12", "p.a.m2": "De acuerdo, Marina. Anoté el pago para el 25/11 y no envío más recordatorios hasta entonces.", "p.a.s2": "agente · 19:12",
      "p.b.l": "LA POLÍTICA ES EL TECHO", "p.b.h": "El agente solo ofrece lo que cabe.", "p.b.o1": "Al contado, 10% de descuento", "p.b.o2": "6 cuotas con pie", "p.b.o3": "aprobación",
      "p.c.l": "COMPROBANTE ≠ CONCILIACIÓN", "p.c.h": "Solo el banco salda la factura.", "p.c.p": "El comprobante queda en espera hasta que el extracto o el webhook del emisor lo confirme.", "p.c.t1": "esperando al banco",
      "p.d.l": "POLÍTICA PREDETERMINADA", "p.d.h": "La ajustas en Configuración.", "p.d.1": "Descuento al contado", "p.d.1v": "hasta 10%", "p.d.2": "Pie mínimo", "p.d.3": "Cuotas", "p.d.3v": "hasta 6", "p.d.4": "Promesa", "p.d.4v": "hasta 15 días",
      "p.e.l": "UNA CUENTA POR EMPRESA", "p.e.h": "Ningún dato se cruza.", "p.e.p": "En un BPO, cada cliente es una cuenta aislada en la base de datos.", "p.e.1": "Clínica", "p.e.2": "Escuela", "p.e.3": "Gimnasio",
      "r.kicker": "Secuencia predeterminada", "r.h2": "Diez etapas alrededor de cada factura.", "r.lede": "La secuencia se ejecuta por horario, sin IA. Toca una etapa para ver qué se envía.",
      "r.h1": "Nada sale fuera del horario de la empresa. Por defecto, de 8 a 20 h, de lunes a sábado.", "r.h2b": "Si pide que paremos, la secuencia se detiene al instante.", "r.h3": "Sin amenazas, sin hablar con terceros y sin cobrar en grupos.",
      "r.core1": "factura", "r.core2": "vence",
      "c.kicker": "Conciliación", "c.h2": "Cada pago que entra encuentra su factura.", "c.lede": "El extracto llega solo, por Open Finance o por el emisor. El matcher se detiene en el primer criterio que cierra, y nada se concilia dos veces.",
      "c.feed": "extracto · cuenta empresa", "c.live": "en vivo", "c.auto": "conciliado", "c.layer": "capa", "c.sugg": "sugerencia", "c.queue": "cola", "c.e3": "nombre parecido, 2 facturas", "c.e4": "sin identificador", "c.boleto": "Boleto", "c.e5": "número de referencia",
      "c.l1h": "txid o E2E idéntico", "c.l1p": "Conciliación automática.", "c.l2h": "Monto, documento y fecha", "c.l2p": "Conciliación automática, de 10 días antes a 60 días después del vencimiento.", "c.l3h": "Monto, nombre parecido y fecha", "c.l3p": "Sugerencia con puntaje para que alguien la confirme.", "c.l4h": "Ningún candidato", "c.l4p": "Va a la cola con todo lo que envió el banco.",
      "g.kicker": "Lo que el código no negocia", "g.h2": "La IA conversa. El dinero queda en manos del código y de tu equipo.",
      "g.1h": "La IA no decide sobre el dinero.", "g.1p": "Lee el comprobante, transcribe el audio y conversa. La secuencia, el cruce y la conciliación son reglas fijas.",
      "g.2h": "El banco confirma la conciliación.", "g.2p": "Un comprobante por sí solo nunca salda una factura. Confirmar sin el banco se rechaza.",
      "g.3h": "Tu política es el techo.", "g.3p": "Pedir 8 cuotas cuando el máximo es 6 pausa al agente y abre una aprobación en el panel.",
      "g.4h": "Una persona tiene la última palabra.", "g.4p": "Dudas en el cruce, disputas, lecturas débiles y facturas en D+30 van a la cola, y se avisa al dueño.",
      "g.5h": "Cobranza sin hostigamiento.", "g.5p": "Mensajes versionados conforme al Código de Defensa del Consumidor de Brasil (CDC, art. 42). La identidad se confirma antes de mostrar cualquier monto.",
      "pr.kicker": "Precio", "pr.h2": "Empieza por la conciliación.", "pr.lede": "Verificar lo que recibes ya paga la cuenta. La secuencia por WhatsApp entra cuando quieras.",
      "pr.phase": "Fase 1 · Conciliación", "pr.fee": "Mensualidad por rango", "pr.setup": "+ configuración única", "pr.p": "Verifica cada PIX y boleto contra la factura correcta, sin hablar con el deudor. Es la puerta de entrada.",
      "pr.t1": "hasta 300 facturas/mes", "pr.t2": "hasta 1.500", "pr.t3": "hasta 5.000",
      "pr.1": "Conciliación de todo el dinero que entra, en cualquier banco", "pr.2": "Archivo del período listo para el contador", "pr.3": "Cola de excepciones para lo que el sistema no cerró solo", "pr.4": "Configuración del emisor e importación de facturas", "pr.cta1": "Empezar por la conciliación",
      "pr.b.phase": "Cobranza + conciliación", "pr.b.fee": "Mensualidad por rango", "pr.b.var": "+ % solo de lo vencido recuperado", "pr.b.p": "El variable se aplica solo a lo que estaba vencido y el banco confirmó. Si no se recupera nada, pagas solo el rango.",
      "pr.b.1": "Todo lo de la conciliación", "pr.b.2": "Secuencia por WhatsApp con plantilla oficial; el recordatorio antes del vencimiento ya está en la mensualidad", "pr.b.3": "Un agente que negocia solo dentro de tu política", "pr.b.4": "Lo recuperado se mide contra la línea base de la implantación", "pr.b.5": "Tope mensual en el variable: la cuenta nunca sorprende",
      "pr.cta": "Hablar del piloto", "pr.note": "El valor de cada rango se define en una conversación, según el tamaño de la cartera. En el piloto, la configuración se descuenta a cambio de un caso de éxito.",
      "f.6q": "¿Qué cuenta como recuperado?", "f.6a": "Una factura pagada después del vencimiento, con el pago confirmado por el banco. Los recordatorios antes del vencimiento y los comprobantes sin extracto no cuentan. El efecto se mide contra la línea base de la implantación, y el variable tiene un tope mensual.",
      "f.1q": "¿Mi banco necesita una integración?", "f.1a": "No. El extracto entra por Open Finance desde cualquier cuenta. Asaas e Inter ya tienen adaptador de emisor. OFX y CSV quedan para excepciones.",
      "f.2q": "¿Y si el deudor envía un comprobante falso?", "f.2a": "Un comprobante nunca salda. Queda esperando al banco y solo se concilia cuando el extracto o el webhook confirma el E2E, el monto y la fecha.",
      "f.3q": "¿El agente puede inventar un descuento?", "f.3a": "No. Las opciones las genera el código a partir de tu política. El agente solo elige entre ellas. Lo que quede fuera va a aprobación.",
      "f.4q": "¿Corro el riesgo de que bloqueen mi número?", "f.4a": "La secuencia usa solo plantillas aprobadas por Meta, con límite de envío y baja inmediata. La cuenta ni siquiera se activa sin el número vinculado y las plantillas aprobadas.",
      "f.5q": "Ya uso Pix Automático. ¿Sigue teniendo sentido?", "f.5a": "Sí. Cuando el débito automático paga, D-3 y D0 salen de la secuencia. Kitou invita a adherirse y avisa cuando el débito falla, además de conciliar lo que entra.",
      "cta.kicker": "Piloto", "cta.h2": "Una cartera, nuestro equipo operándola y el resultado medido contra tu atraso de hoy.", "cta.p": "La cuenta nace apagada y solo se activa con todo en su lugar. Ningún deudor recibe un mensaje antes de tiempo.",
      "cta.1": "Política", "cta.2": "Secuencia y horario", "cta.3": "WhatsApp vinculado", "cta.4": "Plantillas aprobadas", "cta.5": "Base legal", "cta.b1": "Hablar por WhatsApp", "cta.b2": "Ya soy cliente",
      "ft.c1": "PRODUCTO", "ft.c2": "EMPRESA", "ft.agent": "Agente", "ft.rules": "Reglas", "ft.b1": "Cobranza y conciliación por WhatsApp", "ft.b2": "PIX · boleto · Open Finance"
    }
  };
  /* WhatsApp comercial: vem de WHATSAPP_NUMBER no /config.js. Sem número, os botões levam ao bloco do piloto. */
  var WA_NUMBER = String((window.KITOU_CONFIG || {}).whatsappNumber || "").replace(/\D/g, "");
  if (!WA_NUMBER) document.querySelectorAll("[data-wa]").forEach(function (a) { a.removeAttribute("target"); a.removeAttribute("rel"); });
  var WA_MSG = {
    "pt-BR": { pilot: "Olá! Quero conhecer o piloto da Kitou.", price: "Olá! Quero conversar sobre o preço e o piloto da Kitou.", account: "Olá! Quero abrir a conta da minha empresa na Kitou.", float: "Olá! Quero saber mais sobre a Kitou." },
    "en-US": { pilot: "Hi! I'd like to learn about the Kitou pilot.", price: "Hi! I'd like to talk about Kitou's pricing and pilot.", account: "Hi! I'd like to open an account for my company on Kitou.", float: "Hi! I'd like to know more about Kitou." },
    "es": { pilot: "¡Hola! Quiero conocer el piloto de Kitou.", price: "¡Hola! Quiero hablar sobre el precio y el piloto de Kitou.", account: "¡Hola! Quiero abrir la cuenta de mi empresa en Kitou.", float: "¡Hola! Quiero saber más sobre Kitou." }
  };
  var WORDS = { "pt-BR": ["extrato", "Open Finance", "Asaas", "Inter"], "en-US": ["bank statement", "Open Finance", "Asaas", "Inter"], "es": ["extracto", "Open Finance", "Asaas", "Inter"] };
  var LANG_LABEL = { "pt-BR": ["PT-BR", "Idioma: Português (Brasil)"], "en-US": ["EN-US", "Language: English (US)"], "es": ["ES", "Idioma: Español"] };

  /* Etapas da régua por idioma. {v} é o valor, {d} a data de vencimento. */
  var STEPS = {
    "pt-BR": [
      ["D-3", "Lembrete amigável", "Olá, Marina. A mensalidade de novembro, {v}, vence na quinta. O PIX copia-e-cola está aqui embaixo.", "WhatsApp · template oficial"],
      ["D0", "Vence hoje", "Marina, a mensalidade de {v} vence hoje. Se já pagou, pode desconsiderar.", "WhatsApp · template oficial"],
      ["D+1", "Não identificamos o pagamento", "Ainda não identificamos o pagamento de {v}. Segue a 2ª via com o PIX atualizado.", "WhatsApp · template oficial"],
      ["D+3", "Convite a quitar", "A mensalidade de novembro segue em aberto. Quer o PIX de novo ou prefere conversar sobre o pagamento?", "WhatsApp · sem anunciar desconto"],
      ["D+5", "Convite a negociar", "Se ficou difícil pagar de uma vez, responda esta mensagem e vemos juntos uma forma que caiba.", "WhatsApp · sem inventar condição"],
      ["D+7", "Novo convite, com o PIX", "Seguimos à disposição. O PIX da mensalidade de {v} continua valendo.", "WhatsApp · template oficial"],
      ["D+10", "Título em aberto", "Lembrete: a mensalidade de novembro está em aberto. Responda se precisar de ajuda.", "WhatsApp · template oficial"],
      ["D+15", "Última tentativa automática", "Esta é a última mensagem automática sobre a mensalidade de novembro. O PIX segue anexado.", "WhatsApp e e-mail"],
      ["D+21", "A equipe vai assumir", "A partir de agora, uma pessoa da Clínica Demo vai acompanhar este pagamento com você.", "WhatsApp · sem ameaça"],
      ["D+30", "Sai da régua", "O título deixa a régua automática e entra na fila humana do painel. O dono é avisado.", "Painel · fila humana"]
    ],
    "en-US": [
      ["D-3", "Friendly reminder", "Hi Marina. Your November tuition, {v}, is due on Thursday. The PIX copy-and-paste code is right below.", "WhatsApp · official template"],
      ["D0", "Due today", "Marina, your {v} tuition is due today. If you've already paid, please disregard this.", "WhatsApp · official template"],
      ["D+1", "Payment not found", "We haven't found your {v} payment yet. Here is a new copy with an updated PIX code.", "WhatsApp · official template"],
      ["D+3", "Invitation to pay", "Your November tuition is still open. Would you like the PIX code again, or would you rather talk about the payment?", "WhatsApp · no discount announced"],
      ["D+5", "Invitation to negotiate", "If paying all at once got hard, reply to this message and we'll find a way that works for you.", "WhatsApp · no made-up terms"],
      ["D+7", "New invitation, with PIX", "We're here to help. The PIX code for your {v} tuition is still valid.", "WhatsApp · official template"],
      ["D+10", "Invoice still open", "Reminder: your November tuition is still open. Reply if you need help.", "WhatsApp · official template"],
      ["D+15", "Last automatic attempt", "This is the last automatic message about your November tuition. The PIX code is attached.", "WhatsApp and email"],
      ["D+21", "The team takes over", "From now on, someone from Clínica Demo will follow up on this payment with you.", "WhatsApp · no threats"],
      ["D+30", "Leaves the cadence", "The invoice leaves the automatic cadence and joins the dashboard's human queue. The owner is notified.", "Dashboard · human queue"]
    ],
    "es": [
      ["D-3", "Recordatorio amable", "Hola, Marina. La mensualidad de noviembre, {v}, vence el jueves. El PIX copia y pega está aquí abajo.", "WhatsApp · plantilla oficial"],
      ["D0", "Vence hoy", "Marina, la mensualidad de {v} vence hoy. Si ya pagaste, puedes ignorar este mensaje.", "WhatsApp · plantilla oficial"],
      ["D+1", "No identificamos el pago", "Todavía no identificamos el pago de {v}. Te enviamos una nueva copia con el PIX actualizado.", "WhatsApp · plantilla oficial"],
      ["D+3", "Invitación a pagar", "La mensualidad de noviembre sigue abierta. ¿Quieres el PIX de nuevo o prefieres conversar sobre el pago?", "WhatsApp · sin anunciar descuento"],
      ["D+5", "Invitación a negociar", "Si se te complicó pagar de una vez, responde este mensaje y vemos juntos una forma que te funcione.", "WhatsApp · sin inventar condiciones"],
      ["D+7", "Nueva invitación, con el PIX", "Seguimos a tu disposición. El PIX de la mensualidad de {v} sigue vigente.", "WhatsApp · plantilla oficial"],
      ["D+10", "Factura abierta", "Recordatorio: la mensualidad de noviembre está abierta. Responde si necesitas ayuda.", "WhatsApp · plantilla oficial"],
      ["D+15", "Último intento automático", "Este es el último mensaje automático sobre la mensualidad de noviembre. El PIX va adjunto.", "WhatsApp y correo"],
      ["D+21", "El equipo toma el caso", "A partir de ahora, una persona de Clínica Demo acompañará este pago contigo.", "WhatsApp · sin amenazas"],
      ["D+30", "Sale de la secuencia", "La factura sale de la secuencia automática y entra en la cola humana del panel. Se avisa al dueño.", "Panel · cola humana"]
    ]
  };

  /* Guarda o português original de cada trecho para poder voltar */
  var nodes = document.querySelectorAll("[data-i18n]"), ariaNodes = document.querySelectorAll("[data-i18n-aria]");
  nodes.forEach(function (n) { n._pt = n.innerHTML; });
  ariaNodes.forEach(function (n) { n._pt = n.getAttribute("aria-label"); });

  var lang = "pt-BR";
  function money(v, short) { return new Intl.NumberFormat(lang, { style: "currency", currency: "BRL", minimumFractionDigits: short ? 0 : 2, maximumFractionDigits: short ? 0 : 2 }).format(v); }
  function day(iso) { var p = iso.split("-"); return new Intl.DateTimeFormat(lang, { day: "2-digit", month: "2-digit", timeZone: "UTC" }).format(Date.UTC(+p[0], +p[1] - 1, +p[2])); }

  function apply(next, animate) {
    lang = next; var dict = I18N[lang];
    function run() {
      root.lang = lang === "es" ? "es" : lang;
      nodes.forEach(function (n) { var k = n.getAttribute("data-i18n"); n.innerHTML = dict && dict[k] != null ? dict[k] : n._pt; });
      ariaNodes.forEach(function (n) { var k = n.getAttribute("data-i18n-aria"); n.setAttribute("aria-label", dict && dict[k] != null ? dict[k] : n._pt); });
      document.querySelectorAll("[data-brl]").forEach(function (n) { n.textContent = money(+n.getAttribute("data-brl"), n.hasAttribute("data-brl-short")); });
      document.querySelectorAll("[data-date]").forEach(function (n) { n.textContent = day(n.getAttribute("data-date")); });
      document.querySelectorAll("[data-pct]").forEach(function (n) { n.textContent = new Intl.NumberFormat(lang, { style: "percent" }).format(+n.getAttribute("data-pct") / 100); });
      document.querySelectorAll("[data-num]").forEach(function (n) { n.textContent = new Intl.NumberFormat(lang, { maximumFractionDigits: 1 }).format(+n.getAttribute("data-num")); });
      if (WA_NUMBER) document.querySelectorAll("[data-wa]").forEach(function (a) { a.href = "https://wa.me/" + WA_NUMBER + "?text=" + encodeURIComponent(WA_MSG[lang][a.getAttribute("data-wa")]); });
      $("lang-code").textContent = LANG_LABEL[lang][0];
      $("lang-btn").setAttribute("aria-label", LANG_LABEL[lang][1]);
      document.querySelectorAll("#lang-menu [data-lang]").forEach(function (b) { b.setAttribute("aria-checked", String(b.dataset.lang === lang)); });
      wi = 0; rot.innerHTML = "<span>" + WORDS[lang][0] + "</span>";
      buildOrbitLabels(); pick(sel);
      root.classList.remove("swapping");
    }
    if (animate && !reduce) { root.classList.add("swapping"); setTimeout(run, 180); } else run();
    try { localStorage.setItem("kitou-lang", lang); } catch (e) {}
  }
  function $(id) { return document.getElementById(id); }

  /* Menu do idioma */
  var btn = $("lang-btn"), menu = $("lang-menu");
  function openMenu(v) { menu.hidden = !v; btn.setAttribute("aria-expanded", String(v)); if (v) { var c = menu.querySelector('[aria-checked="true"]'); (c || menu.querySelector("button")).focus(); } }
  btn.addEventListener("click", function () { openMenu(menu.hidden); });
  menu.querySelectorAll("[data-lang]").forEach(function (b) { b.addEventListener("click", function () { openMenu(false); btn.focus(); if (b.dataset.lang !== lang) apply(b.dataset.lang, true); }); });
  document.addEventListener("click", function (e) { if (!menu.hidden && !$("lang").contains(e.target)) openMenu(false); });
  menu.addEventListener("keydown", function (e) {
    var items = Array.prototype.slice.call(menu.querySelectorAll("button")), i = items.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    if (e.key === "Escape") { openMenu(false); btn.focus(); }
  });

  /* Aurora */
  var cv = $("aurora"), ctx = cv.getContext("2d");
  var blobs = [
    { c: "rgba(91,67,230,.85)", r: .42, x: .32, y: .28, sx: .00021, sy: .00017 },
    { c: "rgba(154,133,255,.6)", r: .32, x: .7, y: .22, sx: .00017, sy: .00023 },
    { c: "rgba(198,244,50,.22)", r: .22, x: .58, y: .5, sx: .00025, sy: .00013 },
    { c: "rgba(70,50,190,.7)", r: .36, x: .15, y: .55, sx: .00013, sy: .00021 }
  ];
  function size() { var r = cv.getBoundingClientRect(); cv.width = Math.max(1, r.width / 3); cv.height = Math.max(1, r.height / 3); }
  function draw(t) {
    var w = cv.width, h = cv.height; ctx.clearRect(0, 0, w, h);
    blobs.forEach(function (b, i) {
      var x = (b.x + Math.sin(t * b.sx + i) * .08) * w, y = (b.y + Math.cos(t * b.sy + i * 2) * .06) * h, r = b.r * Math.max(w, h);
      var g = ctx.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, b.c); g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    });
    if (!reduce) requestAnimationFrame(draw);
  }
  size(); window.addEventListener("resize", size); requestAnimationFrame(draw);

  /* Palavra que troca */
  var wi = 0, rot = $("rotator");
  if (!reduce) setInterval(function () { var w = WORDS[lang]; wi = (wi + 1) % w.length; rot.innerHTML = "<span>" + w[wi] + "</span>"; }, 2400);

  /* Painel que endireita e rodapé que sobe */
  var dev = $("device"), mark = $("mark");
  function onScroll() {
    var vh = window.innerHeight, r = dev.getBoundingClientRect();
    var p = Math.min(1, Math.max(0, 1 - (r.top - vh * .15) / (vh * .7)));
    dev.style.setProperty("--rx", (22 * (1 - p)).toFixed(2) + "deg"); dev.style.setProperty("--sc", (.92 + .08 * p).toFixed(3));
    var m = mark.getBoundingClientRect(), q = Math.min(1, Math.max(0, (vh - m.top) / (m.height + vh * .2)));
    mark.style.setProperty("--ty", (30 * (1 - q)).toFixed(1) + "%");
  }
  if (!reduce) { window.addEventListener("scroll", onScroll, { passive: true }); onScroll(); }
  else { dev.style.setProperty("--rx", "0deg"); dev.style.setProperty("--sc", "1"); mark.style.setProperty("--ty", "0%"); }

  /* Spotlight */
  document.querySelectorAll(".spot").forEach(function (el) {
    el.addEventListener("pointermove", function (e) { var r = el.getBoundingClientRect(); el.style.setProperty("--x", (e.clientX - r.left) + "px"); el.style.setProperty("--y", (e.clientY - r.top) + "px"); });
  });

  /* Reveal */
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.remove("pending"); io.unobserve(e.target); } }); }, { rootMargin: "0px 0px -8% 0px" });
    document.querySelectorAll(".reveal").forEach(function (el) { if (el.getBoundingClientRect().top > window.innerHeight) { el.classList.add("pending"); io.observe(el); } });
  }

  /* Órbita */
  var orbit = $("orbit"), orbNodes = [], sel = 0, angle = -Math.PI / 2, paused = false;
  STEPS["pt-BR"].forEach(function (s, i) {
    var b = document.createElement("button"); b.type = "button"; b.className = "node" + (i < 2 ? " pre" : i === 9 ? " human" : ""); b.textContent = s[0];
    b.addEventListener("click", function () { pick(i); paused = true; });
    b.addEventListener("pointerenter", function () { paused = true; }); b.addEventListener("pointerleave", function () { paused = false; });
    orbit.appendChild(b); orbNodes.push(b);
  });
  function buildOrbitLabels() { orbNodes.forEach(function (b, i) { var s = STEPS[lang][i]; b.setAttribute("aria-label", s[0] + ": " + s[1]); }); }
  function place() {
    var w = orbit.clientWidth, R = w * .41;
    orbNodes.forEach(function (n, i) { var a = angle + i * (2 * Math.PI / orbNodes.length); n.style.left = (w / 2 + Math.cos(a) * R) + "px"; n.style.top = (w / 2 + Math.sin(a) * R) + "px"; });
  }
  function pick(i) {
    sel = (i + orbNodes.length) % orbNodes.length; var s = STEPS[lang][sel];
    orbNodes.forEach(function (n, j) { n.classList.toggle("on", j === sel); });
    $("d-day").textContent = s[0]; $("d-title").textContent = s[1];
    $("d-text").textContent = s[2].replace("{v}", money(480)); $("d-channel").textContent = s[3];
  }
  $("prev").addEventListener("click", function () { pick(sel - 1); paused = true; });
  $("next").addEventListener("click", function () { pick(sel + 1); paused = true; });
  place(); window.addEventListener("resize", place);
  (function spin() { if (!paused && !reduce) { angle += .0016; place(); } requestAnimationFrame(spin); })();

  /* Matcher */
  var entries = document.querySelectorAll("#feed .entry"), layers = document.querySelectorAll("#layers .layer"), ei = 0;
  function tick() {
    entries.forEach(function (e) { e.classList.remove("flash"); });
    var e = entries[ei]; e.classList.add("flash");
    layers.forEach(function (l) { l.classList.toggle("hit", l.dataset.layer === e.dataset.layer); });
    ei = (ei + 1) % entries.length;
  }
  tick(); if (!reduce) setInterval(tick, 2200);

  /* Idioma inicial: o que a pessoa escolheu antes; senão, português */
  var saved = null; try { saved = localStorage.getItem("kitou-lang"); } catch (e) {}
  apply(I18N[saved] || saved === "pt-BR" ? saved : "pt-BR", false);
})();
