import React, {useEffect, useRef, useState} from 'react';
import {ArrowDown, ArrowUpRight, Check, ChevronRight, ClipboardCheck, Expand, FileText, Github, HeartPulse, Layers3, Maximize2, Minimize2, Radio, ShieldCheck, X} from 'lucide-react';
import './overview.css';

const sourceUrl = 'https://github.com/lauf8/project-salus';
const syntheticUrl = `${sourceUrl}/blob/main/SYNTHETIC_MISSIONS.md`;
const apolloReportUrl = 'https://ntrs.nasa.gov/citations/19700033031';
const assetUrl = name => `${import.meta.env.BASE_URL}${name}`;

const screenshots = {
  measurements: {
    file: 'latest-measurements.webp', width: 1472, height: 694,
    title: 'Latest crew measurements',
    alt: 'Salus dashboard showing the latest vital signs, sleep, fatigue, mood and attention readings, with stale and not evaluated statuses.',
    caption: 'Latest readings in one view. Measurement age and evaluation status stay visible.'
  },
  body: {
    file: 'body-map.webp', width: 623, height: 553,
    title: 'Interactive body map',
    alt: 'Salus body map with labeled locations for vital signs, sleep, fatigue, mood and attention.',
    caption: 'A body map connects each indicator to its measurement history.'
  },
  crew: {
    file: 'crew-overview.webp', width: 1456, height: 685,
    title: 'Crew readiness and well-being overview',
    alt: 'Crew overview showing preflight exams, radiation and space weather, mental well-being, and active health alerts.',
    caption: 'Preflight readiness, radiation context, well-being and active alerts share the overview.'
  },
  alert: {
    file: 'critical-heart-rate-alert.webp', width: 496, height: 322,
    title: 'Active heart rate alert',
    alt: 'An active critical heart rate alert in Salus, with the reading context and actions to acknowledge or resolve it.',
    caption: 'An active clinical alert from a recorded measurement, using the configured simulation rules.'
  },
  predictive: {
    file: 'predictive-summary.webp', width: 1456, height: 374,
    title: 'Predictive Intelligence overview',
    alt: 'Predictive Intelligence dashboard with risk levels, prediction kinds, analysis areas and a pending suggestions count.',
    caption: 'A separate view of rules, anomalies and pending suggestions. Visible counters depend on the selected profile.'
  },
  recommendation: {
    file: 'pending-rest-review.webp', width: 1383, height: 503,
    title: 'Pending rest-period review',
    alt: 'A pending recommendation to review rest periods, showing the responsible role, rationale, documented evidence status and a collapsed NASA references entry.',
    caption: 'A pending rest-period review with its rationale and a NASA references entry. Reference details are collapsed in this capture.'
  },
  mission: {
    file: 'mission-risks.webp', width: 1429, height: 754,
    title: 'Mission risks and recommendations',
    alt: 'Salus mission risk view showing fictional mission risk levels and suggested next actions.',
    caption: 'Mission-level signals and recommendations bring operational context into the same review workflow.'
  }
};

const capabilities = [
  {
    audience: 'Astronauts & flight surgeons', icon: HeartPulse, title: 'Crew health and readiness',
    text: 'Preflight exam requirements and review, astronaut control, vital signs, a body map, sleep, mood, fatigue and measurement history.'
  },
  {
    audience: 'Authorized clinical teams', icon: ClipboardCheck, title: 'Care with the record in view',
    text: 'Clinical occurrences, care records, medication use, allergies, active health alerts and notifications, with access tied to the person and mission role.'
  },
  {
    audience: 'Astronauts & well-being teams', icon: ShieldCheck, title: 'Daily well-being and nutrition',
    text: 'Mental health check-ins and psychologist follow-ups, alongside food inventory, meals, hydration and nutrient totals. Each team sees the records its role permits.'
  },
  {
    audience: 'Mission teams', icon: Radio, title: 'Operations and exposure context',
    text: 'Missions, crew assignments, spacecraft and modules, food supply risks, radiation records and NASA DONKI space-weather events.'
  },
  {
    audience: 'Responsible reviewers', icon: Layers3, title: 'Predictive Intelligence',
    text: 'Rules and anomalies surface changes for review. Tracked recommendations connect the rationale, available document evidence, staff feedback and outcomes. Ollama can assist explanations when configured.'
  }
];

function SourceLink({className = '', children = 'View source'}) {
  return <a className={className} href={sourceUrl} target="_blank" rel="noopener noreferrer"><Github size={18} aria-hidden="true"/>{children}<ArrowUpRight size={16} aria-hidden="true"/></a>;
}

function Actions() {
  return <div className="overview-actions">
    <a className="overview-button overview-button-primary" href="#walkthrough">Explore the product<ArrowDown size={18} aria-hidden="true"/></a>
    <SourceLink className="overview-button overview-button-secondary"/>
  </div>;
}

function Screenshot({name, onEnlarge, priority = false, className = ''}) {
  const screenshot = screenshots[name];
  return <figure className={`overview-screenshot ${className}`}>
    <button className="overview-image-button" type="button" onClick={() => onEnlarge(screenshot)} aria-label={`Enlarge ${screenshot.title.toLowerCase()} screenshot`}>
      <img src={assetUrl(`overview/${screenshot.file}`)} width={screenshot.width} height={screenshot.height} alt={screenshot.alt} loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : 'auto'} decoding="async"/>
      <span className="overview-enlarge"><Expand size={15} aria-hidden="true"/><span>Enlarge</span></span>
    </button>
    <figcaption><span className="overview-demo-label">Demo data</span><span>{screenshot.caption}</span></figcaption>
  </figure>;
}

function ScreenshotViewer({screenshot, onClose}) {
  const dialog = useRef(null);
  const [originalSize, setOriginalSize] = useState(false);

  useEffect(() => {
    const element = dialog.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    element.showModal();
    return () => {
      element.close();
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  return <dialog className="overview-dialog" ref={dialog} aria-labelledby="overview-dialog-title" aria-describedby="overview-dialog-caption" onClose={onClose} onClick={event => { if (event.target === event.currentTarget) dialog.current.close(); }}>
    <div className="overview-dialog-content">
      <header className="overview-dialog-header">
        <div><span className="overview-demo-label">Demo data</span><h2 id="overview-dialog-title">{screenshot.title}</h2></div>
        <button type="button" className="overview-icon-button" onClick={() => dialog.current.close()} aria-label="Close screenshot"><X size={23} aria-hidden="true"/></button>
      </header>
      <div className="overview-dialog-toolbar">
        <span>{originalSize ? 'Scroll to inspect the full image.' : 'Fit to screen'}</span>
        <button type="button" aria-pressed={originalSize} onClick={() => setOriginalSize(value => !value)}>{originalSize ? <Minimize2 size={16} aria-hidden="true"/> : <Maximize2 size={16} aria-hidden="true"/>}{originalSize ? 'Fit to screen' : 'View at original size'}</button>
      </div>
      <div className={`overview-dialog-image${originalSize ? ' overview-dialog-original' : ''}`} tabIndex="0" role="region" aria-label="Screenshot image. Scroll to inspect when viewing at original size.">
        <img src={assetUrl(`overview/${screenshot.file}`)} alt={screenshot.alt} width={screenshot.width} height={screenshot.height}/>
      </div>
      <p className="overview-dialog-caption" id="overview-dialog-caption">{screenshot.caption}</p>
    </div>
  </dialog>;
}

export default function Overview() {
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);

  return <div className="salus-overview">
    <a className="overview-skip" href="#overview-main">Skip to content</a>
    <header className="overview-header">
      <div className="overview-shell overview-header-inner">
        <a className="overview-brand" href="#top" aria-label="Project Salus overview"><img src={assetUrl('salus.png')} alt="Project Salus" width="2172" height="724"/></a>
        <nav aria-label="Overview navigation"><a href="#why-salus">Why Salus</a><a href="#walkthrough">Walkthrough</a><a href="#capabilities">Capabilities</a></nav>
        <SourceLink className="overview-header-source"/>
      </div>
    </header>

    <main id="overview-main">
      <section className="overview-hero" id="top" aria-labelledby="overview-hero-title">
        <div className="overview-shell">
          <p className="overview-eyebrow"><span className="overview-status-dot"/>Crew health. Mission context.</p>
          <h1 id="overview-hero-title">See emerging risks <span>before they escalate.</span></h1>
          <p className="overview-hero-description">Project Salus brings crew health, mission operations, and evidence-linked recommendations into one workspace, so astronauts and flight surgeons can see what changed and decide what to do next.</p>
          <Actions/>
          <div className="overview-hero-product">
            <div className="overview-product-heading"><span><HeartPulse size={17} aria-hidden="true"/>The crew, in context</span><span>Product walkthrough <ChevronRight size={15} aria-hidden="true"/></span></div>
            <Screenshot name="measurements" onEnlarge={setSelectedScreenshot} priority/>
          </div>
          <p className="overview-hero-note">Actual product screens. Fictional demonstration records.</p>
        </div>
      </section>

      <section className="overview-why overview-section" id="why-salus" aria-labelledby="overview-why-title">
        <div className="overview-shell overview-why-layout">
          <div><p className="overview-eyebrow">Why Salus</p><h2 id="overview-why-title">The call is only<br className="overview-desktop-break"/> part of the picture.</h2></div>
          <div className="overview-why-copy"><p>On Apollo 8, Frank Borman fell ill on the way to the Moon. The medical team assessed his condition through recorded crew reports and a conversation from Earth.</p><p>Salus is built around a practical question: what if the team could see the relevant measurements, history and mission context before receiving that call?</p><a className="overview-text-link" href={apolloReportUrl} target="_blank" rel="noopener noreferrer">Read the Apollo 8 mission report<ArrowUpRight size={17} aria-hidden="true"/></a></div>
        </div>
      </section>

      <section className="overview-walkthrough overview-section" id="walkthrough" aria-labelledby="overview-walkthrough-title">
        <div className="overview-shell">
          <div className="overview-section-heading"><p className="overview-eyebrow">The product, step by step</p><h2 id="overview-walkthrough-title">From a measurement<br/>to a reviewed next step.</h2><p>Follow the information through the workspace.</p></div>

          <article className="overview-step" aria-labelledby="overview-monitor-title">
            <div className="overview-monitor-layout">
              <div className="overview-step-copy"><span className="overview-step-number">01 / Monitor</span><h3 id="overview-monitor-title">Monitor the crew.</h3><p>Start with readiness. Then follow the person behind the readings, from vital signs to sleep, mood and fatigue.</p><ul className="overview-check-list"><li><Check size={18} aria-hidden="true"/><span><strong>Before the mission</strong>Review exam requirements and accepted results.</span></li><li><Check size={18} aria-hidden="true"/><span><strong>Across the day</strong>Connect measurements through the body map.</span></li><li><Check size={18} aria-hidden="true"/><span><strong>Over time</strong>Compare with the recorded history and preflight references.</span></li></ul></div>
              <Screenshot name="body" onEnlarge={setSelectedScreenshot} className="overview-body-screenshot"/>
            </div>
            <Screenshot name="crew" onEnlarge={setSelectedScreenshot}/>
          </article>

          <article className="overview-step overview-risk-step" aria-labelledby="overview-risk-title">
            <div className="overview-step-heading"><div><span className="overview-step-number">02 / Identify</span><h3 id="overview-risk-title">Identify emerging risks.</h3></div><p>Keep the current alert and the longer view distinct. Each brings a different kind of attention to the review.</p></div>
            <div className="overview-risk-layout">
              <div className="overview-current-alert"><p className="overview-small-label"><span/>A recent-measurement alert</p><Screenshot name="alert" onEnlarge={setSelectedScreenshot}/></div>
              <div className="overview-forward-copy"><p className="overview-small-label">A signal to look ahead</p><h4>See the change.<br/>Keep its context.</h4><p>Predictive Intelligence uses rules, trends and anomalies to surface changes that may need attention. Mission-level analysis adds supply risks and collective patterns.</p><p>Signals carry their data limits. They support human review and never lower or close an active clinical alert.</p><div className="overview-evidence-note"><FileText size={19} aria-hidden="true"/><span>Rule and anomaly signals are shown here. They are not clinically validated predictions.</span></div></div>
            </div>
            <Screenshot name="predictive" onEnlarge={setSelectedScreenshot}/>
          </article>

          <article className="overview-step overview-review-step" aria-labelledby="overview-review-title">
            <div className="overview-step-heading"><div><span className="overview-step-number">03 / Review</span><h3 id="overview-review-title">Review what to do next.</h3></div><p>Open a pending recommendation. Read the rationale, inspect available evidence and keep the decision with the responsible person.</p></div>
            <Screenshot name="recommendation" onEnlarge={setSelectedScreenshot}/>
            <div className="overview-review-details"><div><span>01</span><h4>Understand the rationale</h4><p>See the signal and context behind the suggested action.</p></div><div><span>02</span><h4>Check the evidence</h4><p>Follow NASA references when available. Missing evidence stays explicit.</p></div><div><span>03</span><h4>Keep a human in the loop</h4><p>Astronauts see their own guidance. Authorized staff review actions and record follow-up.</p></div></div>
          </article>
        </div>
      </section>

      <section className="overview-capabilities overview-section" id="capabilities" aria-labelledby="overview-capabilities-title">
        <div className="overview-shell">
          <div className="overview-section-heading"><p className="overview-eyebrow">Connected workflows</p><h2 id="overview-capabilities-title">One workspace.<br/>Different responsibilities.</h2><p>Health and operations stay connected, with access shaped by each person’s role.</p></div>
          <div className="overview-capability-list">{capabilities.map(({audience, icon: Icon, title, text}) => <div className="overview-capability" key={title}><div className="overview-audience"><Icon size={21} aria-hidden="true"/><span>{audience}</span></div><div><h3>{title}</h3><p>{text}</p></div></div>)}</div>
          <div className="overview-mission-product"><p className="overview-small-label">The operational picture</p><Screenshot name="mission" onEnlarge={setSelectedScreenshot}/></div>
        </div>
      </section>

      <section className="overview-validation overview-section" aria-labelledby="overview-validation-title">
        <div className="overview-shell overview-validation-layout"><div className="overview-validation-number"><span>50</span><p>synthetic missions</p></div><div className="overview-validation-copy"><p className="overview-eyebrow">Built to exercise the workflow</p><h2 id="overview-validation-title">A fictional history.<br/>A concrete way to test.</h2><p>The project includes 50 synthetic missions for functional validation across health records, operations, permissions and recommendations.</p><ul className="overview-mission-states" aria-label="Synthetic mission distribution"><li><strong>35</strong> completed</li><li><strong>10</strong> in progress</li><li><strong>5</strong> planned</li></ul><p className="overview-validation-limit">These records test product behavior. They do not establish clinical accuracy or readiness for real missions.</p><a className="overview-text-link" href={syntheticUrl} target="_blank" rel="noopener noreferrer">Explore the synthetic dataset<ArrowUpRight size={17} aria-hidden="true"/></a></div></div>
      </section>

      <section className="overview-closing overview-section" aria-labelledby="overview-closing-title"><div className="overview-shell"><p className="overview-eyebrow">Project Salus</p><h2 id="overview-closing-title">Keep the next decision<br/>connected to the evidence.</h2><Actions/></div></section>
    </main>

    <footer className="overview-footer"><div className="overview-shell overview-footer-inner"><a className="overview-brand" href="#top" aria-label="Back to the top of Project Salus overview"><img src={assetUrl('salus.png')} alt="Project Salus" width="2172" height="724" loading="lazy"/></a><p>Crew health. Mission operations. Informed review.</p><a className="overview-footer-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">Source on GitHub<ArrowUpRight size={16} aria-hidden="true"/></a></div></footer>
    {selectedScreenshot && <ScreenshotViewer screenshot={selectedScreenshot} onClose={() => setSelectedScreenshot(null)}/>}
  </div>;
}
