import { Schema } from 'mongoose';
import type { ILiteLLMSync } from '~/types';

const litellmSyncModelSchema = new Schema(
  {
    sourceModel: { type: String, required: true },
    litellmModelName: { type: String, required: true },
    litellmModelId: { type: String, default: '' },
  },
  { _id: false },
);

const litellmSyncSchema = new Schema<ILiteLLMSync>(
  {
    endpointName: { type: String, required: true, index: true },
    status: {
      type: String,
      enum: ['pending', 'active', 'failed'],
      default: 'pending',
      required: true,
    },
    virtualKey: { type: String },
    models: { type: [litellmSyncModelSchema], default: [] },
    realBaseURLHash: { type: String },
    lastError: { type: String, default: null },
    lastSyncedAt: { type: Date },
    tenantId: { type: String, index: true },
  },
  { timestamps: true },
);

// One sync record per endpoint per tenant.
litellmSyncSchema.index({ tenantId: 1, endpointName: 1 }, { unique: true });

export default litellmSyncSchema;
