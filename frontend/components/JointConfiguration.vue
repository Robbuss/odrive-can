<template>
    <div class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <UFormField label="Position min (turns)">
                <UInput v-model.number="jointConfiguration.pos_min" type="number" inputmode="decimal" step="0.001"
                    placeholder="e.g. -10.0" />
            </UFormField>

            <UFormField label="Position max (turns)">
                <UInput v-model.number="jointConfiguration.pos_max" type="number" inputmode="decimal" step="0.001"
                    placeholder="e.g. 10.0" />
            </UFormField>
        </div>

        <!-- PID -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <UFormField label="Kp">
                <UInput v-model.number="jointConfiguration.kp" type="number" inputmode="decimal" step="0.001"
                    placeholder="e.g. 1.000" />
            </UFormField>

            <UFormField label="Ki">
                <UInput v-model.number="jointConfiguration.ki" type="number" inputmode="decimal" step="0.001"
                    placeholder="e.g. 0.050" />
            </UFormField>

            <UFormField label="Kd">
                <UInput v-model.number="jointConfiguration.kd" type="number" inputmode="decimal" step="0.001"
                    placeholder="e.g. 0.010" />
            </UFormField>

            <UButton @click="saveConfiguration">Configure</UButton>
        </div>

        <!-- Tiny validity hint -->
        <div v-if="invalidRange" class="text-xs text-amber-600">
            pos_min should be ≤ pos_max.
        </div>
    </div>
</template>

<script setup lang="ts">
import { client as apiClient } from '~/client/client.gen'
import { statusJointJointsJointNameStatusGet, configureJoint } from '~/client/sdk.gen'

apiClient.setConfig({ baseUrl: '/api' })

const props = defineProps<{
    jointName: string
}>()

const { data: jointConfiguration } = await statusJointJointsJointNameStatusGet({
    path: {
        joint_name: props.jointName
    }
})

const invalidRange = computed(() => {
    const min = jointConfiguration?.pos_min
    const max = jointConfiguration?.pos_max
    return min != null && max != null && min > max
})

async function saveConfiguration() {
    await configureJoint({ path: { joint_name: props.jointName }, body: {
        kp: jointConfiguration?.kp,
        ki: jointConfiguration?.ki,
        kd: jointConfiguration?.kd,
        min_pos: jointConfiguration?.pos_min,
        max_pos: jointConfiguration?.pos_max,
    } })
}
</script>
