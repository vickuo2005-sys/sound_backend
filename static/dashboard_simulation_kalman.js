(function(root){
    'use strict';

    // Simulation-only 2D constant-velocity Kalman filter.
    // X and Y are filtered independently with identical 2-state [position, velocity] models.
    // Defaults are engineering starting points only; they are NOT field-validated tuning values.
    const DEFAULT_CONFIG = Object.freeze({
        processAccelerationSigmaMps2: 4,
        defaultMeasurementSigmaM: 25,
        minMeasurementSigmaM: 3,
        maxMeasurementSigmaM: 120,
        measurementIntervalMs: 1000,
        maxPredictionAgeMs: 3000,
        initialVelocitySigmaMps: 25
    });

    const finite = value => typeof value === 'number' && Number.isFinite(value);
    const clamp = (value,min,max) => Math.max(min,Math.min(max,value));
    const point = value => value && finite(value.x) && finite(value.y);

    function createAxis(position, measurementVariance, velocityVariance) {
        return {position, velocity:0, p00:measurementVariance, p01:0, p10:0, p11:velocityVariance};
    }

    function predictAxis(axis, dt, accelerationVariance) {
        const dt2=dt*dt, dt3=dt2*dt, dt4=dt2*dt2;
        const q00=.25*dt4*accelerationVariance;
        const q01=.5*dt3*accelerationVariance;
        const q11=dt2*accelerationVariance;
        return {
            position:axis.position+axis.velocity*dt,
            velocity:axis.velocity,
            p00:axis.p00+dt*(axis.p10+axis.p01)+dt2*axis.p11+q00,
            p01:axis.p01+dt*axis.p11+q01,
            p10:axis.p10+dt*axis.p11+q01,
            p11:axis.p11+q11
        };
    }

    function updateAxis(predicted, measurement, measurementVariance) {
        const innovation=measurement-predicted.position;
        const s=predicted.p00+measurementVariance;
        if(!(s>0) || !finite(s)) return {axis:predicted,innovation,gainPosition:0,gainVelocity:0};
        const k0=predicted.p00/s, k1=predicted.p10/s;
        const p00=(1-k0)*predicted.p00;
        const p01=(1-k0)*predicted.p01;
        const p10=predicted.p10-k1*predicted.p00;
        const p11=predicted.p11-k1*predicted.p01;
        return {
            axis:{
                position:predicted.position+k0*innovation,
                velocity:predicted.velocity+k1*innovation,
                p00,p01,p10,p11
            },
            innovation,
            gainPosition:k0,
            gainVelocity:k1
        };
    }

    class ConstantVelocityKalman2D {
        constructor(config={}) {
            this.config={...DEFAULT_CONFIG,...config};
            this.reset();
        }
        reset() { this.state=null; }
        hasState() { return Boolean(this.state); }
        shouldAcceptMeasurement(timeMs) {
            if(!finite(timeMs)) return false;
            if(!this.state) return true;
            return timeMs-this.state.timeMs>=this.config.measurementIntervalMs;
        }
        measurementSigma(options={}) {
            const candidate=Number(options.uncertaintyM);
            return clamp(
                finite(candidate)?candidate:this.config.defaultMeasurementSigmaM,
                this.config.minMeasurementSigmaM,
                this.config.maxMeasurementSigmaM
            );
        }
        initialize(measurement,timeMs,options={}) {
            const sigma=this.measurementSigma(options), variance=sigma*sigma;
            const velocityVariance=this.config.initialVelocitySigmaMps*this.config.initialVelocitySigmaMps;
            this.state={
                x:createAxis(measurement.x,variance,velocityVariance),
                y:createAxis(measurement.y,variance,velocityVariance),
                timeMs,
                measurementSigmaM:sigma,
                innovationM:0,
                gainPosition:1,
                gainVelocity:0
            };
            return this.snapshot(timeMs,'INITIALIZED');
        }
        predictState(timeMs) {
            if(!this.state||!finite(timeMs)) return null;
            const ageMs=Math.max(0,timeMs-this.state.timeMs);
            if(ageMs>this.config.maxPredictionAgeMs) return null;
            const dt=ageMs/1000;
            const q=this.config.processAccelerationSigmaMps2*this.config.processAccelerationSigmaMps2;
            return {
                x:predictAxis(this.state.x,dt,q),
                y:predictAxis(this.state.y,dt,q),
                timeMs,
                sourceTimeMs:this.state.timeMs,
                ageMs,
                measurementSigmaM:this.state.measurementSigmaM,
                innovationM:this.state.innovationM,
                gainPosition:this.state.gainPosition,
                gainVelocity:this.state.gainVelocity
            };
        }
        snapshot(timeMs=this.state?.timeMs,reason='PREDICTED') {
            const predicted=this.predictState(timeMs);
            if(!predicted) return null;
            const vx=predicted.x.velocity,vy=predicted.y.velocity,speed=Math.hypot(vx,vy);
            const uncertaintyM=Math.sqrt(Math.max(0,(predicted.x.p00+predicted.y.p00)/2));
            return {
                x:predicted.x.position,y:predicted.y.position,vx,vy,speed,
                heading:speed>.05?(Math.atan2(vx,vy)*180/Math.PI+360)%360:null,
                uncertaintyM,
                timeMs:predicted.timeMs,
                sourceTimeMs:predicted.sourceTimeMs,
                ageMs:predicted.ageMs,
                innovationM:predicted.innovationM,
                gainPosition:predicted.gainPosition,
                gainVelocity:predicted.gainVelocity,
                measurementSigmaM:predicted.measurementSigmaM,
                accepted:true,
                reason,
                source:'simulation_kalman_cv'
            };
        }
        predict(timeMs) { return this.snapshot(timeMs,'PREDICTED'); }
        update(measurement,timeMs,options={}) {
            if(!point(measurement)||!finite(timeMs)) return {accepted:false,reason:'INVALID_MEASUREMENT',state:this.predict(timeMs)};
            if(!this.state) return {accepted:true,reason:'INITIALIZED',state:this.initialize(measurement,timeMs,options)};
            const dt=(timeMs-this.state.timeMs)/1000;
            if(!(dt>0)) return {accepted:false,reason:'NON_INCREASING_MEASUREMENT_TIME',state:this.predict(timeMs)};
            const q=this.config.processAccelerationSigmaMps2*this.config.processAccelerationSigmaMps2;
            const px=predictAxis(this.state.x,dt,q),py=predictAxis(this.state.y,dt,q);
            const sigma=this.measurementSigma(options),r=sigma*sigma;
            const ux=updateAxis(px,measurement.x,r),uy=updateAxis(py,measurement.y,r);
            const innovationM=Math.hypot(ux.innovation,uy.innovation);
            this.state={
                x:ux.axis,y:uy.axis,timeMs,
                measurementSigmaM:sigma,
                innovationM,
                gainPosition:(ux.gainPosition+uy.gainPosition)/2,
                gainVelocity:(ux.gainVelocity+uy.gainVelocity)/2
            };
            return {
                accepted:true,reason:'UPDATED',innovationM,
                gainPosition:this.state.gainPosition,
                gainVelocity:this.state.gainVelocity,
                measurementSigmaM:sigma,
                state:this.snapshot(timeMs,'UPDATED')
            };
        }
    }

    const api={DEFAULT_CONFIG,ConstantVelocityKalman2D,predictAxis,updateAxis};
    if(typeof module==='object'&&module.exports)module.exports=api;
    else root.DashboardSimulationKalman=api;
})(typeof globalThis==='object'?globalThis:this);
