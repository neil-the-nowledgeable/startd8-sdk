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
    });
});
