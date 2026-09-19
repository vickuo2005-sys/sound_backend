(function(root){
    'use strict';

    // Mirrors the backend alpha-beta tracker structure for Simulation Lab only.
    // These are engineering defaults, not field-validated tuning values.
    const DEFAULT_CONFIG = Object.freeze({
        alpha: 0.70,
        beta: 0.35,
        alphaMin: 0.35,
        alphaMax: 0.78,
        betaMin: 0.08,
        betaMax: 0.38,
        uncertaintyReferenceM: 20,
        defaultUncertaintyM: 25,
        predictionUncertaintyGrowthMps: 4,
        maxSpeedMps: 80,
        baseGateM: 100,
        measurementIntervalMs: 1000,
        maxPredictionAgeMs: 3000
    });

    const finite = n => typeof n === 'number' && Number.isFinite(n);
    const point = p => p && finite(p.x) && finite(p.y);
    const clamp = (n,a,b) => Math.max(a,Math.min(b,n));
    function gains(config, options={}) {
        const uncertaintyM = finite(Number(options.uncertaintyM)) ? Math.max(0, Number(options.uncertaintyM)) : null;
        const explicitQuality = finite(Number(options.qualityScore)) ? clamp(Number(options.qualityScore),0,1) : null;
        const qualityScore = explicitQuality ?? (uncertaintyM===null ? null : config.uncertaintyReferenceM/(config.uncertaintyReferenceM+uncertaintyM));
        if (qualityScore===null) return {alpha:config.alpha,beta:config.beta,qualityScore:null,uncertaintyM};
        return {
            alpha: config.alphaMin + (config.alphaMax-config.alphaMin)*qualityScore,
            beta: config.betaMin + (config.betaMax-config.betaMin)*qualityScore,
            qualityScore,
            uncertaintyM
        };
    }

    class AlphaBetaTracker {
        constructor(config={}) {
            this.config = {...DEFAULT_CONFIG, ...config};
            this.reset();
        }

        reset() {
            this.state = null;
            this.lastMeasurementSignature = null;
        }

        hasState() {
            return Boolean(this.state);
        }

        predict(timeMs) {
            if (!this.state || !finite(timeMs)) return null;
            const dt = Math.max(0, (timeMs - this.state.timeMs) / 1000);
            const ageMs = Math.max(0, timeMs - this.state.timeMs);
            if (ageMs > this.config.maxPredictionAgeMs) return null;
            const uncertaintyM = Math.max(0, Number(this.state.uncertaintyM)||0) + this.config.predictionUncertaintyGrowthMps * dt;
            return {
                x: this.state.x + this.state.vx * dt,
                y: this.state.y + this.state.vy * dt,
                vx: this.state.vx,
                vy: this.state.vy,
                uncertaintyM,
                qualityScore: this.state.qualityScore ?? null,
                alphaUsed: this.state.alphaUsed ?? this.config.alpha,
                betaUsed: this.state.betaUsed ?? this.config.beta,
                speed: Math.hypot(this.state.vx, this.state.vy),
                heading: Math.hypot(this.state.vx, this.state.vy) > 0.05
                    ? (Math.atan2(this.state.vx, this.state.vy) * 180 / Math.PI + 360) % 360
                    : null,
                timeMs,
                sourceTimeMs: this.state.timeMs,
                ageMs,
                innovationM: this.state.innovationM || 0,
                accepted: true,
                source: 'simulation_alpha_beta_track'
            };
        }

        shouldAcceptMeasurement(timeMs) {
            if (!finite(timeMs)) return false;
            if (!this.state) return true;
            return timeMs - this.state.timeMs >= this.config.measurementIntervalMs;
        }

        update(measurement, timeMs, options={}) {
            if (!point(measurement) || !finite(timeMs)) {
                return {accepted:false, reason:'INVALID_MEASUREMENT', state:this.predict(timeMs)};
            }

            if (!this.state) {
                const adaptive = gains(this.config, options);
                const uncertaintyM = adaptive.uncertaintyM ?? this.config.defaultUncertaintyM;
                this.state = {
                    x: measurement.x,
                    y: measurement.y,
                    vx: 0,
                    vy: 0,
                    timeMs,
                    innovationM: 0,
                    uncertaintyM,
                    qualityScore: adaptive.qualityScore,
                    alphaUsed: adaptive.alpha,
                    betaUsed: adaptive.beta
                };
                return {accepted:true, reason:'INITIALIZED', innovationM:0, uncertaintyM, qualityScore:adaptive.qualityScore, alphaUsed:adaptive.alpha, betaUsed:adaptive.beta, state:this.predict(timeMs)};
            }

            const dt = (timeMs - this.state.timeMs) / 1000;
            if (!(dt > 0)) {
                return {accepted:false, reason:'NON_INCREASING_MEASUREMENT_TIME', innovationM:0, state:this.predict(timeMs)};
            }

            const predictedX = this.state.x + this.state.vx * dt;
            const predictedY = this.state.y + this.state.vy * dt;
            const residualX = measurement.x - predictedX;
            const residualY = measurement.y - predictedY;
            const innovationM = Math.hypot(residualX, residualY);
            const adaptive = gains(this.config, options);
            const measurementUncertaintyM = adaptive.uncertaintyM ?? this.config.defaultUncertaintyM;
            const predictedUncertaintyM = Math.max(0, Number(this.state.uncertaintyM)||0) + this.config.predictionUncertaintyGrowthMps * dt;
            const maxSpeed = Math.max(0.1, this.config.maxSpeedMps);
            const gateM = Math.max(0, this.config.baseGateM) + maxSpeed * dt + measurementUncertaintyM;

            if (innovationM > gateM) {
                return {
                    accepted:false,
                    reason:'INNOVATION_GATE_EXCEEDED',
                    innovationM,
                    gateM,
                    state:this.predict(timeMs)
                };
            }

            const filteredX = predictedX + adaptive.alpha * residualX;
            const filteredY = predictedY + adaptive.alpha * residualY;
            const vx = this.state.vx + adaptive.beta * residualX / dt;
            const vy = this.state.vy + adaptive.beta * residualY / dt;
            const speed = Math.hypot(vx, vy);

            if (!finite(speed) || speed > maxSpeed) {
                return {
                    accepted:false,
                    reason:'SPEED_LIMIT_EXCEEDED',
                    innovationM,
                    gateM,
                    candidateSpeedMps:speed,
                    state:this.predict(timeMs)
                };
            }

            const uncertaintyM = Math.max(
                2,
                (1-adaptive.alpha)*predictedUncertaintyM + adaptive.alpha*measurementUncertaintyM + Math.min(innovationM,gateM)*0.05
            );
            this.state = {
                x: filteredX,
                y: filteredY,
                vx,
                vy,
                timeMs,
                innovationM,
                uncertaintyM,
                qualityScore: adaptive.qualityScore,
                alphaUsed: adaptive.alpha,
                betaUsed: adaptive.beta
            };

            return {
                accepted:true,
                reason:'UPDATED',
                innovationM,
                gateM,
                uncertaintyM,
                qualityScore:adaptive.qualityScore,
                alphaUsed:adaptive.alpha,
                betaUsed:adaptive.beta,
                state:this.predict(timeMs)
            };
        }
    }

    const api = {DEFAULT_CONFIG, gains, AlphaBetaTracker};
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.DashboardSimulationTracker = api;
})(typeof globalThis === 'object' ? globalThis : this);
