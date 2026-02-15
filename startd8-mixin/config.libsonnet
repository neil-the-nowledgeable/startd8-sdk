{
  _config+:: {
    // Datasource UIDs - override these to match your Grafana instance
    datasources: {
      tempo: { uid: 'tempo', type: 'tempo' },
      loki: { uid: 'loki', type: 'loki' },
      mimir: { uid: 'mimir', type: 'prometheus' },
    },

    // Dashboard defaults
    dashboardTags: ['startd8', 'sdk'],
    dashboardRefresh: '30s',
    dashboardTimeFrom: 'now-6h',
    dashboardTimeTo: 'now',

    // Service name default
    serviceName: 'startd8-sdk',

    // Session tracking metrics (meter: startd8)
    metrics: {
      activeSessions: 'startd8_active_sessions',
      requestsTotal: 'startd8_requests_total',
      tokensTotal: 'startd8_tokens_total',
      responseTimeMs: 'startd8_response_time_ms',
      contextUsageRatio: 'startd8_context_usage_ratio',
      truncationsTotal: 'startd8_truncations_total',
      costTotal: 'startd8_cost_total',
      // Cost tracking metrics (meter: startd8.costs)
      costInputTokens: 'startd8_cost_input_tokens',
      costOutputTokens: 'startd8_cost_output_tokens',
      costPerRequest: 'startd8_cost_per_request',
      budgetLimit: 'startd8_budget_limit',
      // Event bridge metric (meter: startd8.events)
      eventsTotal: 'startd8_events_total',
    },

    // Span patterns for TraceQL queries
    spans: {
      agentGenerate: 'agent.generate',
      workflow: 'workflow.',
      pipeline: 'pipeline.',
      artisanWorkflow: 'artisan.workflow.',
      phaseRunner: 'PhaseRunner.run',
    },

    // Artisan contractor metrics (from ContextCore task emitter)
    artisanMetrics: {
      weightedProgress: 'project_weighted_progress',
      tasksTotal: 'project_tasks_total',
      phaseProgress: 'project_phase_progress',
      taskPercentComplete: 'project_task_percent_complete',
      storyPointsTotal: 'project_story_points_total',
      estimatedLocTotal: 'project_estimated_loc_total',
      blockersActive: 'project_blockers_active',
      completionRate: 'project_completion_rate',
      criticalPathProgress: 'project_critical_path_progress',
      tasksByType: 'project_tasks_by_type',
      tasksByPriority: 'project_tasks_by_priority',
      effortTotal: 'project_effort_total',
      qualityScoreAvg: 'project_quality_score_avg',
      featureCostUsd: 'project_contextcore_feature_cost_usd',
      integrationSuccess: 'project_contextcore_integration_success',
    },

    // Alert thresholds
    alertThresholds: {
      truncationRate: 0.05,
      contextCapacity: 0.9,
      budgetDailyUsd: 100,
    },

    // Common label selectors
    selectors: {
      serviceName: 'service_name=~"$service_name"',
      model: 'model=~"$model"',
      projectId: 'project_id=~"$project_id"',
      agentName: 'agent_name=~"$agent_name"',
    },
  },
}
