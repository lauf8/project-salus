export const defaultTourSeconds = 42;

export const narratedTourSteps = [
  {id: 'top', narration: 'On future space missions, astronauts will be too far from Earth to wait for help.'},
  {id: 'problem', narration: 'Today, health care in space is reactive: a problem happens, and only then is it treated.'},
  {id: 'data', narration: 'Project Salus changes that. It brings together astronauts’ physical and mental health data, spacecraft conditions, and NASA space weather events.'},
  {id: 'prediction', narration: 'Using artificial intelligence, it anticipates risks'},
  {id: 'alerts', narration: 'and alerts the medical team before they become problems.'},
  {id: 'learning', narration: 'And with every mission, it learns and gets more accurate.'},
  {id: 'closing', narration: 'Project Salus: to predict is to protect.'}
];

const wordCount = text => text.trim().split(/\s+/).filter(Boolean).length;

export function tourDurationFromSearch(search) {
  const params = new URLSearchParams(search);
  if (!params.has('tour')) return null;
  const seconds = Number(params.get('tour'));
  return Number.isFinite(seconds) && seconds > 0 ? seconds : defaultTourSeconds;
}

export function tourSchedule(steps, totalSeconds) {
  const totalWords = steps.reduce((sum, step) => sum + wordCount(step.narration), 0);
  let elapsedWords = 0;
  return steps.map(step => {
    const startSeconds = Math.round(totalSeconds * elapsedWords / totalWords * 10) / 10;
    elapsedWords += wordCount(step.narration);
    return {id: step.id, startSeconds};
  });
}
