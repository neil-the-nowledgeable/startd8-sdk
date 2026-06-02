import { z } from "zod";

/**
 * Zod schemas mirroring prisma/schema.prisma field-by-field.
 *
 * The Prisma schema is the source of truth; these schemas must not invent,
 * omit, or drift from it. Field-mapping convention:
 *
 *   Prisma            Zod
 *   ---------------   ------------------------------------
 *   String            z.string()
 *   String?           z.string().nullable()        (null on the wire, not undefined)
 *   Boolean           z.boolean()
 *   Int               z.number().int()
 *   Int?              z.number().int().nullable()
 *   Float             z.number()
 *   Float?            z.number().nullable()
 *   DateTime          z.string().datetime()        (ISO-8601 wire format)
 *   Json              z.unknown()
 *   @id field         z.string()                   (CUIDs are strings)
 *
 * Fields with @default(...) are kept present in these base schemas (the server
 * fills the default); only input variants would mark them .optional().
 * Format hints: `email` → .email(), names ending in `Url`/`url` → .url(),
 * applied without changing nullability. No constraints beyond what Prisma or
 * the field-name semantics justify. Relation fields are virtual (not columns)
 * and are excluded; only scalar columns and their FK columns appear here.
 */

// ─── Profile ──────────────────────────────────────────────────────────────────

export const ProfileSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  name: z.string(),
  title: z.string().nullable(),
  company: z.string().nullable(),
  industry: z.string().nullable(),
  summary: z.string().nullable(),
  linkedinUrl: z.string().url().nullable(),
  email: z.string().email().nullable(),
  phone: z.string().nullable(),
  location: z.string().nullable(),
  yearsExp: z.number().int().nullable(),
  notes: z.string().nullable(),
});

// ─── ProofPoint ───────────────────────────────────────────────────────────────

export const ProofPointSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  title: z.string().nullable(),
  description: z.string().nullable(),
  context: z.string().nullable(),
  result: z.string().nullable(),
  impact: z.string().nullable(),
  timeframe: z.string().nullable(),
  role: z.string().nullable(),
  notes: z.string().nullable(),
});

// ─── Capability ───────────────────────────────────────────────────────────────

export const CapabilitySchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  name: z.string().nullable(),
  category: z.string().nullable(),
  description: z.string().nullable(),
  proficiency: z.string().nullable(),
  notes: z.string().nullable(),
});

// ─── Outcome ──────────────────────────────────────────────────────────────────

export const OutcomeSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  name: z.string().nullable(),
  category: z.string().nullable(),
  description: z.string().nullable(),
  metric: z.string().nullable(),
  timeframe: z.string().nullable(),
  notes: z.string().nullable(),
});

// ─── Metric ───────────────────────────────────────────────────────────────────

export const MetricSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  name: z.string().nullable(),
  value: z.string().nullable(),
  unit: z.string().nullable(),
  direction: z.string().nullable(),
  timeframe: z.string().nullable(),
  description: z.string().nullable(),
  notes: z.string().nullable(),
});

// ─── Differentiator ───────────────────────────────────────────────────────────

export const DifferentiatorSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  name: z.string().nullable(),
  category: z.string().nullable(),
  description: z.string().nullable(),
  evidence: z.string().nullable(),
  notes: z.string().nullable(),
});

// ─── ValueProp ────────────────────────────────────────────────────────────────

export const ValuePropSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  headline: z.string().nullable(),
  subheadline: z.string().nullable(),
  body: z.string().nullable(),
  audience: z.string().nullable(),
  format: z.string().nullable(),
  notes: z.string().nullable(),
});

// ─── Artifact ─────────────────────────────────────────────────────────────────

export const ArtifactSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  kind: z.string().nullable(),
  title: z.string().nullable(),
  url: z.string().url().nullable(),
  description: z.string().nullable(),
  mimeType: z.string().nullable(),
  sizeBytes: z.number().int().nullable(),
  notes: z.string().nullable(),
});

// ─── AiCall ───────────────────────────────────────────────────────────────────

export const AiCallSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  model: z.string().nullable(),
  promptTokens: z.number().int().nullable(),
  responseTokens: z.number().int().nullable(),
  costUsd: z.number().nullable(),
  purpose: z.string().nullable(),
  requestBody: z.string().nullable(),
  responseBody: z.string().nullable(),
  durationMs: z.number().int().nullable(),
  error: z.string().nullable(),
});

// ─── ProofPointCapability (join table) ──────────────────────────────────────────

export const ProofPointCapabilitySchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  proofPointId: z.string(),
  capabilityId: z.string(),
});

// ─── ProofPointOutcome (join table) ─────────────────────────────────────────────

export const ProofPointOutcomeSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  proofPointId: z.string(),
  outcomeId: z.string(),
});

// ─── CapabilityOutcome (join table) ─────────────────────────────────────────────

export const CapabilityOutcomeSchema = z.object({
  id: z.string(),
  ownerId: z.string(),
  source: z.string(),
  confirmed: z.boolean(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  capabilityId: z.string(),
  outcomeId: z.string(),
});

// ─── Composite schema ─────────────────────────────────────────────────────────
// Client-facing aggregate per docs/PLAN.md §2: aiCalls and the join tables are
// server-internal and omitted from the composite.

export const ValueModelSchema = z.object({
  profile: ProfileSchema,
  proofPoints: z.array(ProofPointSchema),
  capabilities: z.array(CapabilitySchema),
  outcomes: z.array(OutcomeSchema),
  metrics: z.array(MetricSchema),
  differentiators: z.array(DifferentiatorSchema),
  valueProps: z.array(ValuePropSchema),
  artifacts: z.array(ArtifactSchema),
});

// ─── Inferred TypeScript types ────────────────────────────────────────────────

export type Profile = z.infer<typeof ProfileSchema>;
export type ProofPoint = z.infer<typeof ProofPointSchema>;
export type Capability = z.infer<typeof CapabilitySchema>;
export type Outcome = z.infer<typeof OutcomeSchema>;
export type Metric = z.infer<typeof MetricSchema>;
export type Differentiator = z.infer<typeof DifferentiatorSchema>;
export type ValueProp = z.infer<typeof ValuePropSchema>;
export type Artifact = z.infer<typeof ArtifactSchema>;
export type AiCall = z.infer<typeof AiCallSchema>;
export type ProofPointCapability = z.infer<typeof ProofPointCapabilitySchema>;
export type ProofPointOutcome = z.infer<typeof ProofPointOutcomeSchema>;
export type CapabilityOutcome = z.infer<typeof CapabilityOutcomeSchema>;

export type ValueModel = {
  profile: Profile;
  proofPoints: ProofPoint[];
  capabilities: Capability[];
  outcomes: Outcome[];
  metrics: Metric[];
  differentiators: Differentiator[];
  valueProps: ValueProp[];
  artifacts: Artifact[];
};
