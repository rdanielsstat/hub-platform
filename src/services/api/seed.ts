import type { Note, Project } from './types'

const DAY = 24 * 60 * 60 * 1000

function daysAgo(n: number): string {
  return new Date(Date.now() - n * DAY).toISOString()
}

function daysAhead(n: number): string {
  return new Date(Date.now() + n * DAY).toISOString().slice(0, 10)
}

/**
 * Seed projects from the brainstorm in the spec, so the dashboard is never
 * empty on first load.
 */
export const seedProjects: Project[] = [
  {
    id: 'p-incubator',
    name: 'This Incubator',
    pitch:
      'The platform itself: one home to capture, triage, and graduate every idea.',
    description:
      'A personal platform to capture, organize, and triage project ideas where any idea can graduate into a real, standalone build, but there is a place for all of them. Exists to stop the scatter, not to become a thing endlessly polished instead of shipping.',
    status: 'Active',
    tags: ['meta', 'tools'],
    excitement: 5,
    effort: 3,
    potential: 4,
    nextAction: 'Ship the dashboard read/create milestone.',
    targetDate: daysAhead(14),
    links: ['https://github.com', 'https://vercel.com'],
    createdAt: daysAgo(30),
    updatedAt: daysAgo(0),
  },
  {
    id: 'p-stocks',
    name: 'Stock Analytics / TA Platform',
    pitch: 'Technical-analysis and stats platform for market data.',
    description:
      'Build a technical analysis platform surfacing statistical signals over market data. High effort but a strong personal-interest overlap of stats and stocks.',
    status: 'Inbox',
    tags: ['stats', 'stocks'],
    excitement: 4,
    effort: 5,
    potential: 4,
    nextAction: 'Sketch the core indicators and data source.',
    targetDate: null,
    links: [],
    createdAt: daysAgo(24),
    updatedAt: daysAgo(24),
  },
  {
    id: 'p-cms-hospital',
    name: 'CMS Hospital Quality Benchmarking',
    pitch: 'Benchmark hospital quality using public CMS datasets.',
    description:
      'Use public CMS datasets to benchmark hospital quality metrics. Strong expertise moat given healthcare + stats background.',
    status: 'Exploring',
    tags: ['healthcare', 'stats'],
    excitement: 4,
    effort: 4,
    potential: 5,
    nextAction: 'Pull a sample CMS dataset and profile it.',
    targetDate: null,
    links: [],
    createdAt: daysAgo(21),
    updatedAt: daysAgo(6),
  },
  {
    id: 'p-health-hub',
    name: 'Personal Health-Data Analytics Hub',
    pitch: 'Unify personal health + fitness data into one analytics view.',
    description:
      'Aggregate personal health and fitness data sources into a single analytics hub for trends and insights.',
    status: 'Inbox',
    tags: ['healthcare', 'stats', 'fitness'],
    excitement: 3,
    effort: 4,
    potential: 3,
    nextAction: 'List the data sources worth pulling first.',
    targetDate: null,
    links: [],
    createdAt: daysAgo(19),
    updatedAt: daysAgo(19),
  },
  {
    id: 'p-hiking',
    name: 'Hiking / Outdoor Analytics',
    pitch: 'Analytics over hikes and outdoor activity across California.',
    description:
      'Track and analyze hiking and outdoor activity with a California focus: routes, elevation, frequency, conditions.',
    status: 'Parked',
    tags: ['outdoors', 'fitness', 'california'],
    excitement: 3,
    effort: 3,
    potential: 2,
    nextAction: 'Decide whether to reuse the health hub data layer.',
    targetDate: null,
    links: [],
    createdAt: daysAgo(40),
    updatedAt: daysAgo(35),
  },
  {
    id: 'p-chess',
    name: 'Chess Improvement Analytics',
    pitch: 'Turn game history into a targeted improvement plan.',
    description:
      'Analyze chess game history to surface recurring mistakes and a focused improvement plan. High excitement, low-ish effort.',
    status: 'Exploring',
    tags: ['chess', 'stats'],
    excitement: 5,
    effort: 2,
    potential: 3,
    nextAction: 'Export game archive from Lichess/Chess.com API.',
    targetDate: daysAhead(30),
    links: ['https://lichess.org/api'],
    createdAt: daysAgo(15),
    updatedAt: daysAgo(3),
  },
  {
    id: 'p-gsd',
    name: 'German Shepherd Health/Activity Tracker',
    pitch: 'Track a dog’s health and activity over time.',
    description:
      'A tracker for a German Shepherd’s health and activity: weight, exercise, vet visits, and trends.',
    status: 'Inbox',
    tags: ['dogs'],
    excitement: 3,
    effort: 2,
    potential: 2,
    nextAction: 'Define the minimal daily log entry.',
    targetDate: null,
    links: [],
    createdAt: daysAgo(12),
    updatedAt: daysAgo(12),
  },
  {
    id: 'p-jobsearch',
    name: 'Job-Search + Application Tracker',
    pitch: 'A pipeline tracker for job applications and follow-ups.',
    description:
      'Track job applications through a pipeline with statuses, follow-ups, and notes per company.',
    status: 'Parked',
    tags: ['career'],
    excitement: 2,
    effort: 2,
    potential: 3,
    nextAction: 'Reassess if/when actively searching.',
    targetDate: null,
    links: [],
    createdAt: daysAgo(50),
    updatedAt: daysAgo(48),
  },
  {
    id: 'p-spanish',
    name: 'Spanish Learning Helper',
    pitch: 'A focused helper for practicing and retaining Spanish.',
    description:
      'A learning helper for Spanish practice: spaced repetition, vocab, and conversational drills.',
    status: 'Inbox',
    tags: ['spanish', 'learning'],
    excitement: 3,
    effort: 3,
    potential: 2,
    nextAction: 'Pick one drill type to prototype.',
    targetDate: null,
    links: [],
    createdAt: daysAgo(9),
    updatedAt: daysAgo(9),
  },
  {
    id: 'p-consulting',
    name: 'Consulting Client Site / Portal',
    pitch: 'A client-facing portal for consulting engagements.',
    description:
      'A site/portal for consulting clients: deliverables, updates, and a healthcare-focused engagement surface.',
    status: 'Killed',
    tags: ['consulting', 'healthcare'],
    excitement: 2,
    effort: 4,
    potential: 2,
    nextAction: 'Shelved. Revisit only with a concrete client need.',
    targetDate: null,
    links: [],
    createdAt: daysAgo(60),
    updatedAt: daysAgo(45),
  },
]

export const seedNotes: Note[] = [
  {
    id: 'n-1',
    projectId: 'p-incubator',
    body: 'Kicked off the v1 build. Keeping layers clean: data → api → UI. No agent layer yet.',
    createdAt: daysAgo(30),
  },
  {
    id: 'n-2',
    projectId: 'p-incubator',
    body: 'Decided quick-capture is the front door: name + pitch, everything else optional.',
    createdAt: daysAgo(5),
  },
  {
    id: 'n-3',
    projectId: 'p-chess',
    body: 'Lichess has a clean public API for game archives. Good starting point.',
    createdAt: daysAgo(3),
  },
  {
    id: 'n-4',
    projectId: 'p-cms-hospital',
    body: 'The expertise moat here is real: worth exploring before the flashier ideas.',
    createdAt: daysAgo(6),
  },
]
