import { PanelPlugin } from '@grafana/data';
import { StakeholdersPanel } from './components/StakeholdersPanel';
import { StakeholdersPanelOptions } from './types';

export const plugin = new PanelPlugin<StakeholdersPanelOptions>(StakeholdersPanel).setPanelOptions((builder) => {
  builder
    .addTextInput({
      path: 'datasourceUid',
      name: 'Run datasource UID',
      description:
        'UID of the datasource that proxies /stakeholders/* to the run endpoint and adds the bearer ' +
        'token server-side. Do NOT put a token here — it would be world-readable in the dashboard JSON.',
      defaultValue: '',
      category: ['Connection'],
    })
    .addNumberInput({
      path: 'defaultCap',
      name: 'Default cap',
      description: 'Default max personas to query (empty = all). Bounds spend.',
      category: ['Run'],
    })
    .addRadio({
      path: 'mode',
      name: 'Panel mode',
      description:
        'Pick by what you need. Run = ask ALL personas ONE question → answers in seconds (cheap; the ' +
        '“survey”). Facilitate = a multi-ROUND deliberation → a synthesis you can triage into the ' +
        'backlog/pipeline (fire-and-poll, minutes, pricier; the “workshop”). Apply = the FR-R7 write ' +
        'gate that commits proposals to the project source of record (preview → paste challenge → ' +
        'ratify). Start with Run; use Facilitate when you need a synthesis, not just answers. All ' +
        'token-gated, not human-proof; output is synthetic + unratified.',
      defaultValue: 'run',
      settings: {
        options: [
          { value: 'run', label: 'Run — 1 question, all personas' },
          { value: 'facilitate', label: 'Facilitate — multi-round synthesis' },
          { value: 'apply', label: 'Apply — write gate' },
        ],
      },
      category: ['Connection'],
    })
    .addRadio({
      path: 'posture',
      name: 'Facilitate posture',
      description:
        'Facilitate mode only. Scrutiny = strategic red-team (assumptions gate can halt). ' +
        'Prototype = constructive early-stage UX (non-blocking).',
      defaultValue: 'scrutiny',
      settings: {
        options: [
          { value: 'scrutiny', label: 'Scrutiny' },
          { value: 'prototype', label: 'Prototype' },
        ],
      },
      showIf: (o) => o.mode === 'facilitate',
      category: ['Facilitate'],
    })
    .addRadio({
      path: 'tier',
      name: 'Facilitate model tier',
      description:
        'Facilitate mode only. Premium = opus/gpt-5.5/gemini-pro (higher cost). ' +
        'Cheap = haiku/mini/flash (de-correlated, lower cost).',
      defaultValue: 'premium',
      settings: {
        options: [
          { value: 'premium', label: 'Premium' },
          { value: 'cheap', label: 'Cheap' },
        ],
      },
      showIf: (o) => o.mode === 'facilitate',
      category: ['Facilitate'],
    });
});
