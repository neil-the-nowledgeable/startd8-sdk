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
        'Run = the paid stakeholder Q&A. Apply = the FR-R7 write gate (preview → paste challenge → ' +
        'ratify) that writes the project source of record. Token-gated, not human-proof.',
      defaultValue: 'run',
      settings: {
        options: [
          { value: 'run', label: 'Run' },
          { value: 'apply', label: 'Apply' },
        ],
      },
      category: ['Connection'],
    });
});
