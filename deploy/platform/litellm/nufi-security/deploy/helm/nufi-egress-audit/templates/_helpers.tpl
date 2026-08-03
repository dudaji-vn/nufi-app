{{- define "nufi.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nufi.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "nufi.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nufi.labels" -}}
app.kubernetes.io/name: {{ include "nufi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end -}}

{{- define "nufi.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nufi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "nufi.image" -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
