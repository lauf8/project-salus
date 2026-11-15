import React, {useEffect, useRef, useState} from 'react';
import {Activity, ArrowDown, ArrowUpRight, BellRing, Brain, CircleDot, ClipboardCheck, Expand, FileText, Github, GitBranch, HeartPulse, Maximize2, Minimize2, Orbit, RefreshCcw, Rocket, ShieldCheck, Sparkles, Sun, TrendingUp, X} from 'lucide-react';
import {narratedTourSteps, tourDurationFromSearch, tourSchedule} from './overview-tour.js';
import './overview.css';

const sourceUrl = 'https://github.com/lauf8/project-salus';
const syntheticUrl = `${sourceUrl}/blob/main/SYNTHETIC_MISSIONS.md`;
const predictiveUrl = `${sourceUrl}/blob/main/PREDICTIVE_INTELLIGENCE.md`;
const apolloReportUrl = 'https://ntrs.nasa.gov/citations/19700033031';
const assetUrl = name => `${import.meta.env.BASE_URL}${name}`;

const screenshots = {
  measurements: {
    file: 'latest-measurements.webp', width: 1472, height: 694,
    title: 'Latest crew measurements',
    alt: 'Salus dashboard showing the latest vital signs, sleep, fatigue, mood and attention readings, with stale and not evaluated statuses.',
    caption: 'Every reading keeps its time, context and evaluation status, so the models know what they can trust.'
  },
  crew: {
    file: 'crew-overview.webp', width: 1456, height: 685,
    title: 'Crew readiness and well-being overview',
    alt: 'Crew overview showing preflight exams, radiation and space weather exposure, mental well-being check-ins, and active health alerts.',
    caption: 'Preflight readiness, radiation exposure, mental well-being and active alerts in one view.'
  },
  history: {
    file: 'measurement-history.webp', width: 1435, height: 785,
    title: 'Measurement history',
    alt: 'Resting heart rate history for one astronaut with collection time, value, context, quality and note for each reading.',
    caption: 'Time-stamped history becomes each astronaut’s individual baseline. Recorder names are masked.'
  },
  predictive: {
    file: 'predictive-summary.webp', width: 1456, height: 374,
    title: 'Predictive Intelligence overview',
    alt: 'Predictive Intelligence dashboard with monitored missions, risks identified by level and pending recommendations.',
    caption: 'Risks identified across missions, by level, with the recommendations waiting for review.'
  },
  cardiovascular: {
    file: 'pending-cardiovascular-review.webp', width: 1414, height: 430,
    title: 'Pending cardiovascular review',
    alt: 'A pending recommendation asking the flight surgeon to review a persistent resting heart rate shift from the individual baseline, with urgency within 72 hours and NASA references.',
    caption: 'A persistent resting heart rate shift sends a review to the flight surgeon within 72 hours.'
  },
  recommendation: {
    file: 'pending-rest-review.webp', width: 1383, height: 503,
    title: 'Pending rest-period review',
    alt: 'A pending recommendation to review rest periods after a resting heart rate increase with reduced sleep, with urgency within 24 hours and NASA references.',
    caption: 'Heart rate rising while sleep drops: a combined signal ranked for review within 24 hours.'
  },
  alert: {
    file: 'critical-heart-rate-alert.webp', width: 496, height: 322,
    title: 'Active clinical alert',
    alt: 'An active critical heart rate alert in Salus, with the reading context and alert history.',
    caption: 'Clinical alerts stay separate. A prediction never lowers or closes one.'
  },
  mission: {
    file: 'mission-risks.webp', width: 1429, height: 754,
    title: 'Mission-level predictions',
    alt: 'Mission list with the last predictive analysis, signals such as food shortage, food expiration, collective fatigue and collective well-being decline, and the highest risk level.',
    caption: 'Mission-level signals: food shortage, food expiration, collective fatigue and well-being decline.'
  },
  food: {
    file: 'food-inventory.webp', width: 1429, height: 736,
    title: 'Food inventory',
    alt: 'Mission food inventory listing packaged meals, water and their storage status.',
    caption: 'Inventory and consumption feed the supply projection.'
  }
};

const detailCards = [
  {file: 'heart-rate-detail.webp', alt: 'Heart rate card showing 59 bpm with the measurement time.'},
  {file: 'sleep-quality-detail.webp', alt: 'Sleep quality card with the latest self-reported score.'},
  {file: 'fatigue-detail.webp', alt: 'Fatigue card with the latest self-reported score.'},
  {file: 'mood-detail.webp', alt: 'Mood card with the latest self-reported score.'}
];

const dataStreams = [
  {icon: HeartPulse, title: 'Physical health', text: 'Heart rate, blood pressure, oxygen saturation, temperature, glucose, sleep, fatigue and nutrition intake.'},
  {icon: Brain, title: 'Mental health', text: 'Check-ins on stress, mood, energy, isolation, workload and crew connection, plus psychologist follow-ups.'},
  {icon: Rocket, title: 'Spacecraft conditions', text: 'Spacecraft and modules, recurring onboard occurrences, food stock and expiration across the mission.'},
  {icon: Sun, title: 'NASA space weather', text: 'Solar flares, coronal mass ejections and solar particle events from NASA DONKI, linked to radiation exposure.'}
];

const predictionSteps = [
  {icon: CircleDot, title: 'Learn each astronaut’s normal', text: 'Preflight references or the astronaut’s own history become a personal baseline. No one is compared to a generic average.'},
  {icon: TrendingUp, title: 'Track the trend', text: 'Rolling 24-hour, 7-day and 30-day windows and a 14-day slope show where each indicator is heading.'},
  {icon: Activity, title: 'Catch deviations and anomalies', text: 'A sustained shift of two standard deviations from baseline, or an outlier reading, raises a signal.'},
  {icon: GitBranch, title: 'Connect the signals', text: 'Heart rate with reduced sleep, stress with mood, crew-wide fatigue. Combined patterns surface earlier than any single value.'},
  {icon: Sparkles, title: 'Forecast the next 24 hours', text: 'Machine learning models estimate near-term risk, such as elevated fatigue tomorrow. Probabilities appear only when a model passes validation and calibration.'}
];

const predictionDomains = ['Cardiovascular', 'Sleep and fatigue', 'Psychological', 'Nutrition', 'Food supply', 'Crew-wide trends', 'Spacecraft occurrences', 'Radiation follow-up'];

const learningLoop = [
  {title: 'Predict', text: 'Signals and forecasts from the latest data.'},
  {title: 'Review', text: 'The responsible specialist accepts or rejects each suggestion.'},
  {title: 'Act', text: 'Executed actions are recorded with what was done.'},
  {title: 'Measure', text: 'Before and after values show whether it helped.'},
  {title: 'Improve', text: 'Outcomes re-rank future suggestions. New data retrains the models.'}
];

const syntheticMetrics = [
  {label: 'PR-AUC', value: '0.62', baseline: '0.35 persistence baseline'},
  {label: 'Brier score', value: '0.050', baseline: '0.075 baseline (lower is better)'},
  {label: 'Calibration error', value: '0.039', baseline: 'Gate requires 0.10 or less'}
];

function SourceLink({className = '', children = 'View source'}) {
  return <a className={className} href={sourceUrl} target="_blank" rel="noopener noreferrer"><Github size={18} aria-hidden="true"/>{children}<ArrowUpRight size={16} aria-hidden="true"/></a>;
}

function Actions() {
  return <div className="overview-actions">
    <a className="overview-button overview-button-primary" href="#prediction">See how it predicts<ArrowDown size={18} aria-hidden="true"/></a>
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

const chartDays = [61, 60, 62, 59, 61, 60, 63, 65, 67, 68, 71, 72, 74, 76];
const chartX = day => 40 + day * 40;
const chartY = value => 230 - (value - 54) * 6.5;
const chartPath = chartDays.map((value, day) => `${day ? 'L' : 'M'}${chartX(day)} ${chartY(value)}`).join(' ');

function PredictionTimeline() {
  return <figure className="overview-timeline">
    <figcaption className="overview-timeline-heading">
      <span><TrendingUp size={17} aria-hidden="true"/>Resting heart rate against the astronaut’s own baseline</span>
      <span className="overview-timeline-tag">Illustration</span>
    </figcaption>
    <svg viewBox="0 0 680 270" role="img" aria-labelledby="overview-timeline-title overview-timeline-description">
      <title id="overview-timeline-title">Prediction before the problem</title>
      <desc id="overview-timeline-description">Resting heart rate stays inside the personal baseline band for seven days, then rises steadily. Salus raises a signal on day nine, four days before symptoms would be reported in a reactive workflow.</desc>
      <rect className="overview-timeline-band" x="40" y={chartY(64)} width="520" height={chartY(57) - chartY(64)} rx="4"/>
      <text className="overview-timeline-band-label" x="48" y={chartY(57) + 18}>Personal baseline</text>
      {[0, 7, 13].map(day => <text key={day} className="overview-timeline-axis" x={chartX(day)} y="262" textAnchor="middle">Day {day + 1}</text>)}
      <line className="overview-timeline-marker overview-timeline-salus" x1={chartX(8)} x2={chartX(8)} y1="28" y2="245"/>
      <line className="overview-timeline-marker overview-timeline-reactive" x1={chartX(12)} x2={chartX(12)} y1="28" y2="245"/>
      <path className="overview-timeline-line" d={chartPath}/>
      {chartDays.map((value, day) => <circle key={day} className={day >= 8 ? 'overview-timeline-point overview-timeline-point-alert' : 'overview-timeline-point'} cx={chartX(day)} cy={chartY(value)} r="4.5"/>)}
      <text className="overview-timeline-label overview-timeline-label-salus" x={chartX(8) - 8} y="20" textAnchor="end">Salus alerts the team</text>
      <text className="overview-timeline-label overview-timeline-label-reactive" x={chartX(12) + 8} y="20">Reactive care starts</text>
      <text className="overview-timeline-gain" x={chartX(10)} y="56" textAnchor="middle">4 days earlier</text>
    </svg>
  </figure>;
}

function useNarratedTour() {
  useEffect(() => {
    const duration = tourDurationFromSearch(window.location.search);
    if (!duration) return undefined;
    const timers = tourSchedule(narratedTourSteps, duration).map(({id, startSeconds}) => window.setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({behavior: 'smooth', block: 'start'});
    }, startSeconds * 1000));
    const stop = () => timers.forEach(window.clearTimeout);
    window.addEventListener('keydown', stop, {once: true});
    return () => {
      stop();
      window.removeEventListener('keydown', stop);
    };
  }, []);
}

export default function Overview() {
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);
  useNarratedTour();

  return <div className="salus-overview">
    <a className="overview-skip" href="#overview-main">Skip to content</a>
    <header className="overview-header">
      <div className="overview-shell overview-header-inner">
        <a className="overview-brand" href="#top" aria-label="Project Salus overview"><img src={assetUrl('salus.png')} alt="Project Salus" width="2172" height="724"/></a>
        <nav aria-label="Overview navigation"><a href="#problem">The problem</a><a href="#data">Data</a><a href="#prediction">Prediction</a><a href="#learning">Learning</a></nav>
        <SourceLink className="overview-header-source"/>
      </div>
    </header>

    <main id="overview-main">
      <section className="overview-hero" id="top" aria-labelledby="overview-hero-title">
        <div className="overview-shell">
          <p className="overview-eyebrow"><span className="overview-status-dot"/>Predictive health for deep space crews</p>
          <h1 id="overview-hero-title">To predict <span>is to protect.</span></h1>
          <p className="overview-hero-description">On future space missions, astronauts will be too far from Earth to wait for help. Project Salus combines crew health, spacecraft conditions and NASA space weather to anticipate risks and alert the medical team before they become problems.</p>
          <Actions/>
          <div className="overview-hero-product overview-hero-prediction">
            <PredictionTimeline/>
          </div>
          <p className="overview-hero-note">Illustrative curve. Product screens below use fictional demonstration records.</p>
        </div>
      </section>

      <section className="overview-why overview-section" id="problem" aria-labelledby="overview-problem-title">
        <div className="overview-shell">
          <div className="overview-why-layout">
            <div><p className="overview-eyebrow">The problem</p><h2 id="overview-problem-title">Health care in space<br className="overview-desktop-break"/> is still reactive.</h2></div>
            <div className="overview-why-copy"><p>Today, a problem happens and only then is it treated. Near Earth, help is hours away. On the way to Mars, a single message can take up to 22 minutes to arrive, and evacuation is not an option.</p><p>On Apollo 8, Frank Borman fell ill on the way to the Moon. The medical team could only assess him through crew reports and a conversation from Earth, after the symptoms had started.</p><a className="overview-text-link" href={apolloReportUrl} target="_blank" rel="noopener noreferrer">Read the Apollo 8 mission report<ArrowUpRight size={17} aria-hidden="true"/></a></div>
          </div>
          <div className="overview-compare" role="list" aria-label="Reactive care compared with Project Salus">
            <div className="overview-compare-card" role="listitem"><p className="overview-small-label">Reactive care</p><ol><li>A problem happens</li><li>The crew reports symptoms</li><li>Treatment starts</li></ol></div>
            <div className="overview-compare-card overview-compare-salus" role="listitem"><p className="overview-small-label">With Project Salus</p><ol><li>Data shows an early change</li><li>The medical team is alerted</li><li>Action comes before the problem</li></ol></div>
          </div>
        </div>
      </section>

      <section className="overview-section overview-data" id="data" aria-labelledby="overview-data-title">
        <div className="overview-shell">
          <div className="overview-section-heading"><p className="overview-eyebrow">One picture of the crew</p><h2 id="overview-data-title">Four data streams.<br/>One continuous view.</h2><p>Salus brings together what is usually scattered across separate systems, so every prediction starts from the full context.</p></div>
          <div className="overview-stream-list">{dataStreams.map(({icon: Icon, title, text}) => <div className="overview-stream" key={title}><Icon size={22} aria-hidden="true"/><h3>{title}</h3><p>{text}</p></div>)}</div>
          <div className="overview-detail-strip" aria-label="Individual indicator cards">{detailCards.map(card => <img key={card.file} src={assetUrl(`overview/${card.file}`)} alt={card.alt} width="470" height="205" loading="lazy" decoding="async"/>)}</div>
          <div className="overview-data-screens">
            <Screenshot name="measurements" onEnlarge={setSelectedScreenshot}/>
            <Screenshot name="crew" onEnlarge={setSelectedScreenshot}/>
          </div>
        </div>
      </section>

      <section className="overview-section overview-prediction" id="prediction" aria-labelledby="overview-prediction-title">
        <div className="overview-shell">
          <div className="overview-section-heading"><p className="overview-eyebrow">Artificial intelligence</p><h2 id="overview-prediction-title">How Salus anticipates risk.</h2><p>Rules, statistics and machine learning work on every astronaut and every mission, continuously, in the background.</p></div>
          <ol className="overview-pipeline">{predictionSteps.map(({icon: Icon, title, text}, index) => <li key={title}><span className="overview-pipeline-index">{String(index + 1).padStart(2, '0')}</span><Icon size={22} aria-hidden="true"/><h3>{title}</h3><p>{text}</p></li>)}</ol>
          <div className="overview-stats" role="list" aria-label="Prediction engine facts">
            <div role="listitem"><strong>24 h</strong><span>forecast horizon</span></div>
            <div role="listitem"><strong>3</strong><span>time windows per indicator</span></div>
            <div role="listitem"><strong>8</strong><span>risk areas analyzed</span></div>
            <div role="listitem"><strong>0</strong><span>clinical alerts lowered by a prediction</span></div>
          </div>
          <ul className="overview-domain-list" aria-label="Risk areas">{predictionDomains.map(domain => <li key={domain}>{domain}</li>)}</ul>
          <div className="overview-prediction-screens">
            <Screenshot name="history" onEnlarge={setSelectedScreenshot}/>
            <Screenshot name="predictive" onEnlarge={setSelectedScreenshot}/>
          </div>
        </div>
      </section>

      <section className="overview-section overview-alerts" id="alerts" aria-labelledby="overview-alerts-title">
        <div className="overview-shell">
          <div className="overview-step-heading"><div><p className="overview-eyebrow"><BellRing size={14} aria-hidden="true"/>Early warning</p><h2 id="overview-alerts-title">Alert the medical team<br/>before it becomes a problem.</h2></div><p>Each risk turns into a ranked, time-bound review for the right specialist, with the reason, the data behind it and NASA references.</p></div>
          <Screenshot name="recommendation" onEnlarge={setSelectedScreenshot}/>
          <Screenshot name="cardiovascular" onEnlarge={setSelectedScreenshot}/>
          <div className="overview-review-details"><div><span>01</span><h4>The right person</h4><p>Flight surgeon, psychologist, nutritionist or mission planner, according to the risk.</p></div><div><span>02</span><h4>The right time</h4><p>Urgency within 24 or 72 hours, ranked by evidence, context and past outcomes.</p></div><div><span>03</span><h4>A human decision</h4><p>Salus suggests. The responsible specialist decides. Nothing runs automatically.</p></div></div>
          <div className="overview-risk-layout overview-alerts-safety">
            <div className="overview-current-alert"><p className="overview-small-label"><span/>Clinical alerts stay in charge</p><Screenshot name="alert" onEnlarge={setSelectedScreenshot}/></div>
            <div className="overview-forward-copy"><p className="overview-small-label">Mission scale</p><h4>Beyond one astronaut.</h4><p>Salus also projects food stock against consumption, flags expiring supplies, and detects fatigue or well-being declining across the crew.</p><p>Where data is missing, such as spacecraft telemetry or bone density, Salus says so explicitly instead of guessing.</p><div className="overview-evidence-note"><ShieldCheck size={19} aria-hidden="true"/><span>Predictions support the medical team. They are preventive indicators, not diagnoses.</span></div></div>
          </div>
          <div className="overview-mission-product"><Screenshot name="mission" onEnlarge={setSelectedScreenshot}/></div>
        </div>
      </section>

      <section className="overview-section overview-learning" id="learning" aria-labelledby="overview-learning-title">
        <div className="overview-shell">
          <div className="overview-section-heading"><p className="overview-eyebrow"><RefreshCcw size={14} aria-hidden="true"/>Continuous learning</p><h2 id="overview-learning-title">Every mission makes<br/>the next one safer.</h2><p>Every decision and outcome is recorded, so Salus learns which signals matter and which actions work.</p></div>
          <ol className="overview-loop">{learningLoop.map(({title, text}, index) => <li key={title}><span>{String(index + 1).padStart(2, '0')}</span><h3>{title}</h3><p>{text}</p></li>)}</ol>
          <div className="overview-learning-layout">
            <div className="overview-learning-copy">
              <h3>Accuracy is earned, not assumed.</h3>
              <p>New models are trained offline on mission history and must beat simple baselines before anyone can activate them. Active models are monitored and flagged when their accuracy degrades. Previous versions can be restored at any time.</p>
              <a className="overview-text-link" href={predictiveUrl} target="_blank" rel="noopener noreferrer">Read the Predictive Intelligence design<ArrowUpRight size={17} aria-hidden="true"/></a>
            </div>
            <div className="overview-metrics" aria-labelledby="overview-metrics-title">
              <p className="overview-small-label" id="overview-metrics-title">Fatigue forecast, next 24 hours</p>
              <dl>{syntheticMetrics.map(({label, value, baseline}) => <div key={label}><dt>{label}</dt><dd><strong>{value}</strong><span>{baseline}</span></dd></div>)}</dl>
              <p className="overview-metrics-note"><FileText size={16} aria-hidden="true"/>Measured on a synthetic cohort to verify the pipeline. Not clinical validation.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="overview-validation overview-section" aria-labelledby="overview-validation-title">
        <div className="overview-shell overview-validation-layout"><div className="overview-validation-number"><span>50</span><p>synthetic missions</p></div><div className="overview-validation-copy"><p className="overview-eyebrow">Built to be tested</p><h2 id="overview-validation-title">A fictional history.<br/>A concrete way to test.</h2><p>The project includes 50 synthetic missions to exercise health records, operations, permissions, predictions and recommendations end to end.</p><ul className="overview-mission-states" aria-label="Synthetic mission distribution"><li><strong>35</strong> completed</li><li><strong>10</strong> in progress</li><li><strong>5</strong> planned</li></ul><p className="overview-validation-limit">These records test product behavior. They do not establish clinical accuracy or readiness for real missions.</p><a className="overview-text-link" href={syntheticUrl} target="_blank" rel="noopener noreferrer">Explore the synthetic dataset<ArrowUpRight size={17} aria-hidden="true"/></a></div></div>
      </section>

      <section className="overview-closing overview-section" id="closing" aria-labelledby="overview-closing-title"><div className="overview-shell"><p className="overview-eyebrow"><Orbit size={14} aria-hidden="true"/>Project Salus</p><h2 id="overview-closing-title">To predict<br/>is to protect.</h2><p className="overview-closing-copy"><ClipboardCheck size={18} aria-hidden="true"/>Crew health, spacecraft conditions and space weather, turned into early warnings for the medical team.</p><Actions/></div></section>
    </main>

    <footer className="overview-footer"><div className="overview-shell overview-footer-inner"><a className="overview-brand" href="#top" aria-label="Back to the top of Project Salus overview"><img src={assetUrl('salus.png')} alt="Project Salus" width="2172" height="724" loading="lazy"/></a><p>Project Salus: to predict is to protect.</p><a className="overview-footer-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">Source on GitHub<ArrowUpRight size={16} aria-hidden="true"/></a></div></footer>
    {selectedScreenshot && <ScreenshotViewer screenshot={selectedScreenshot} onClose={() => setSelectedScreenshot(null)}/>}
  </div>;
}
