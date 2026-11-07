'use strict';

(function attachSimulationPrediction(root) {
    const EARTH_RADIUS_M = 6371000;
    const DEFAULT_HORIZONS_SEC = Object.freeze([5, 10, 15, 30]);
    const DEFAULTS = Object.freeze({
        estimator_window_sec: 5,
        estimator_tau_sec: 2,
        minimum_points: 3,
        minimum_history_sec: 2,
        maximum_history_gap_sec: 3,
        minimum_motion_speed_mps: 0.5,
        radial_speed_tolerance_mps: 0.1,
        distance_trend_tolerance_m: 0.5,
        eta_search_horizon_sec: 300,
        discriminant_epsilon: 1e-7,
        speed_epsilon: 1e-9
    });

    function finite(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }
    function clamp(value, lower, upper) { return Math.max(lower, Math.min(upper, value)); }
    function toRadians(value) { return value * Math.PI / 180; }
    function toDegrees(value) { return value * 180 / Math.PI; }
    function normalizeHeadingDeg(value) { return ((value % 360) + 360) % 360; }
    function normalizeLongitudeRad(value) {
        return ((value + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    }
    function circularDifferenceDeg(a, b) {
        const difference = Math.abs(normalizeHeadingDeg(a) - normalizeHeadingDeg(b));
        return Math.min(difference, 360 - difference);
    }
    function validPosition(point) {
        const lat = finite(point?.lat); const lng = finite(point?.lng);
        return lat !== null && lng !== null && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
    }
    function siteProtectedRadiusM(site) {
        return finite(site?.protected_radius_m ?? site?.radius_m);
    }
    function localOffsetMeters(origin, target) {
        const lat0 = toRadians(origin.lat); const lat1 = toRadians(target.lat);
        const deltaLat = lat1 - lat0;
        const deltaLng = normalizeLongitudeRad(toRadians(target.lng) - toRadians(origin.lng));
        const meanLat = (lat0 + lat1) / 2;
        return {
            east_m: deltaLng * EARTH_RADIUS_M * Math.cos(meanLat),
            north_m: deltaLat * EARTH_RADIUS_M
        };
    }
    function localOffsetToLatLng(origin, eastM, northM) {
        const lat0 = toRadians(origin.lat);
        const lat = lat0 + northM / EARTH_RADIUS_M;
        const cosine = Math.max(1e-12, Math.abs(Math.cos(lat0)));
        const lng = toRadians(origin.lng) + eastM / (EARTH_RADIUS_M * cosine);
        return {
            simulation: true,
            lat: toDegrees(lat),
            lng: toDegrees(normalizeLongitudeRad(lng))
        };
    }
    function haversineDistanceM(a, b) {
        const lat1 = toRadians(a.lat); const lat2 = toRadians(b.lat);
        const deltaLat = lat2 - lat1;
        const deltaLng = normalizeLongitudeRad(toRadians(b.lng) - toRadians(a.lng));
        const raw = Math.sin(deltaLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLng / 2) ** 2;
        const term = clamp(raw, 0, 1);
        return 2 * EARTH_RADIUS_M * Math.atan2(Math.sqrt(term), Math.sqrt(Math.max(0, 1 - term)));
    }
    function computeBearingToSite(position, site) {
        const lat1 = toRadians(position.lat); const lat2 = toRadians(site.lat);
        const deltaLng = normalizeLongitudeRad(toRadians(site.lng) - toRadians(position.lng));
        const y = Math.sin(deltaLng) * Math.cos(lat2);
        const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(deltaLng);
        return normalizeHeadingDeg(toDegrees(Math.atan2(y, x)));
    }
    function velocityFromSpeedHeading(speedMps, headingDeg) {
        const heading = toRadians(normalizeHeadingDeg(headingDeg));
        return {
            east_mps: speedMps * Math.sin(heading),
            north_mps: speedMps * Math.cos(heading)
        };
    }
    function speedHeadingFromVelocity(eastMps, northMps) {
        return {
            speed_mps: Math.hypot(eastMps, northMps),
            heading_deg: normalizeHeadingDeg(toDegrees(Math.atan2(eastMps, northMps)))
        };
    }
    function normalizeSimulationHistory(history) {
        const reasons = [];
        const byTimestamp = new Map();
        for (const input of Array.isArray(history) ? history : []) {
            const t = finite(input?.t ?? input?.timestamp_sec);
            if (t === null) { reasons.push('INVALID_TIME'); continue; }
            if (!validPosition(input)) { reasons.push('INVALID_POSITION'); continue; }
            byTimestamp.set(t, {simulation:true, t, lat:Number(input.lat), lng:Number(input.lng)});
        }
        const points = [...byTimestamp.values()].sort((a, b) => a.t - b.t);
        return {simulation:true, points, status_reasons:[...new Set(reasons)]};
    }
    function unwrapHeadings(samples) {
        if (!Array.isArray(samples) || !samples.length) return [];
        const result = [{...samples[0], heading_deg:normalizeHeadingDeg(samples[0].heading_deg)}];
        for (let index = 1; index < samples.length; index += 1) {
            const normalized = normalizeHeadingDeg(samples[index].heading_deg);
            const previous = result[index - 1].heading_deg;
            let candidate = normalized;
            while (candidate - previous > 180) candidate -= 360;
            while (candidate - previous < -180) candidate += 360;
            result.push({...samples[index], heading_deg:candidate});
        }
        return result;
    }
    function estimateTurnRate(samples, tauSec = DEFAULTS.estimator_tau_sec) {
        const unwrapped = unwrapHeadings(samples);
        if (unwrapped.length < 2) return null;
        const latestTime = unwrapped[unwrapped.length - 1].t;
        let weightSum = 0; let weightedTime = 0; let weightedHeading = 0;
        for (const sample of unwrapped) {
            const weight = Math.exp(-(latestTime - sample.t) / tauSec);
            weightSum += weight; weightedTime += weight * sample.t; weightedHeading += weight * sample.heading_deg;
        }
        if (weightSum <= 0) return null;
        const meanTime = weightedTime / weightSum; const meanHeading = weightedHeading / weightSum;
        let covariance = 0; let variance = 0;
        for (const sample of unwrapped) {
            const weight = Math.exp(-(latestTime - sample.t) / tauSec);
            covariance += weight * (sample.t - meanTime) * (sample.heading_deg - meanHeading);
            variance += weight * (sample.t - meanTime) ** 2;
        }
        return variance <= 1e-12 ? null : covariance / variance;
    }
    function evaluatePredictionDataQuality(history, options = {}) {
        const settings = {...DEFAULTS, ...options};
        const normalized = normalizeSimulationHistory(history);
        const reasons = [...normalized.status_reasons];
        const points = normalized.points;
        const latestTime = points[points.length - 1]?.t;
        const recent = latestTime === undefined ? [] : points.filter(point => point.t >= latestTime - settings.estimator_window_sec);
        if (recent.length < settings.minimum_points) reasons.push('TOO_FEW_POINTS');
        if (recent.length >= 2 && recent[recent.length - 1].t - recent[0].t < settings.minimum_history_sec) reasons.push('HISTORY_TOO_SHORT');
        for (let index = 1; index < recent.length; index += 1) {
            if (recent[index].t - recent[index - 1].t > settings.maximum_history_gap_sec) { reasons.push('HISTORY_GAP'); break; }
        }
        let pathLengthM = 0;
        for (let index = 1; index < recent.length; index += 1) pathLengthM += haversineDistanceM(recent[index - 1], recent[index]);
        const uncertainty = finite(options.position_uncertainty_m);
        if (uncertainty !== null && uncertainty > pathLengthM) reasons.push('UNCERTAINTY_EXCEEDS_MOTION');
        const uniqueReasons = [...new Set(reasons)];
        return {simulation:true, status:uniqueReasons.length ? 'DATA_INSUFFICIENT' : 'OK', status_reasons:uniqueReasons, points:recent, path_length_m:pathLengthM};
    }
    function estimateMotionState(history, options = {}) {
        const settings = {...DEFAULTS, ...options};
        const normalized = normalizeSimulationHistory(history);
        const points = normalized.points;
        if (points.length < 2) return null;
        const latestTime = points[points.length - 1].t;
        const recent = points.filter(point => point.t >= latestTime - settings.estimator_window_sec);
        if (recent.length < settings.minimum_points) return null;
        let eastWeighted = 0; let northWeighted = 0; let weightSum = 0;
        const headingSamples = [];
        for (let index = 1; index < recent.length; index += 1) {
            const start = recent[index - 1]; const end = recent[index]; const deltaTime = end.t - start.t;
            if (!(deltaTime > 0) || deltaTime > settings.maximum_history_gap_sec) continue;
            const offset = localOffsetMeters(start, end);
            const east = offset.east_m / deltaTime; const north = offset.north_m / deltaTime;
            const weight = Math.exp(-(latestTime - end.t) / settings.estimator_tau_sec);
            eastWeighted += weight * east; northWeighted += weight * north; weightSum += weight;
            headingSamples.push({t:end.t, heading_deg:speedHeadingFromVelocity(east, north).heading_deg});
        }
        if (weightSum <= 0 || headingSamples.length < 2) return null;
        const eastMps = eastWeighted / weightSum; const northMps = northWeighted / weightSum;
        const motion = speedHeadingFromVelocity(eastMps, northMps);
        return {
            simulation:true,
            east_mps:eastMps,
            north_mps:northMps,
            speed_mps:motion.speed_mps,
            heading_deg:motion.heading_deg,
            turn_rate_deg_s:estimateTurnRate(headingSamples, settings.estimator_tau_sec)
        };
    }
    function projectConstantVelocity(current, velocity, horizonsSec = DEFAULT_HORIZONS_SEC) {
        return horizonsSec.map(horizon => ({
            simulation:true,
            horizon_sec:horizon,
            ...localOffsetToLatLng(current, velocity.east_mps * horizon, velocity.north_mps * horizon)
        }));
    }
    function projectConstantTurn(current, speedMps, headingDeg, turnRateDegS, horizonsSec = DEFAULT_HORIZONS_SEC) {
        const omega = toRadians(turnRateDegS); const heading = toRadians(normalizeHeadingDeg(headingDeg));
        if (Math.abs(omega) < 1e-9) return projectConstantVelocity(current, velocityFromSpeedHeading(speedMps, headingDeg), horizonsSec);
        return horizonsSec.map(horizon => {
            const east = (speedMps / omega) * (Math.cos(heading) - Math.cos(heading + omega * horizon));
            const north = (speedMps / omega) * (Math.sin(heading + omega * horizon) - Math.sin(heading));
            return {simulation:true, horizon_sec:horizon, ...localOffsetToLatLng(current, east, north)};
        });
    }
    function computeRadialClosingSpeed(current, site, velocity) {
        const towardSite = localOffsetMeters(current, site); const range = Math.hypot(towardSite.east_m, towardSite.north_m);
        if (range <= 1e-9) return 0;
        return velocity.east_mps * towardSite.east_m / range + velocity.north_mps * towardSite.north_m / range;
    }
    function computeClosestPointOfApproach(current, site, velocity, horizonSec = DEFAULTS.eta_search_horizon_sec) {
        const siteToCurrent = localOffsetMeters(site, current);
        const speedSquared = velocity.east_mps ** 2 + velocity.north_mps ** 2;
        if (speedSquared <= DEFAULTS.speed_epsilon) return {simulation:true, reliable:false, reason:'LOW_SPEED', time_sec:null, raw_time_sec:null, distance_m:haversineDistanceM(current, site)};
        const rawTime = -(siteToCurrent.east_m * velocity.east_mps + siteToCurrent.north_m * velocity.north_mps) / speedSquared;
        const time = clamp(rawTime, 0, horizonSec);
        const east = siteToCurrent.east_m + velocity.east_mps * time;
        const north = siteToCurrent.north_m + velocity.north_mps * time;
        return {simulation:true, reliable:true, reason:rawTime < 0 ? 'DEPARTING' : 'OK', time_sec:time, raw_time_sec:rawTime, distance_m:Math.hypot(east, north)};
    }
    function computeProtectedRadiusIntersection(current, site, velocity, options = {}) {
        const settings = {...DEFAULTS, ...options}; const radius = siteProtectedRadiusM(site);
        const siteToCurrent = localOffsetMeters(site, current);
        const currentDistance = Math.hypot(siteToCurrent.east_m, siteToCurrent.north_m);
        if (currentDistance <= radius) return {simulation:true, status:'AT_SITE', eta_sec:0, discriminant:null};
        const a = velocity.east_mps ** 2 + velocity.north_mps ** 2;
        if (a <= settings.speed_epsilon) return {simulation:true, status:'LOW_SPEED', eta_sec:null, discriminant:null};
        const b = 2 * (siteToCurrent.east_m * velocity.east_mps + siteToCurrent.north_m * velocity.north_mps);
        const c = siteToCurrent.east_m ** 2 + siteToCurrent.north_m ** 2 - radius ** 2;
        let discriminant = b ** 2 - 4 * a * c;
        if (discriminant < 0 && discriminant >= -settings.discriminant_epsilon) discriminant = 0;
        if (discriminant < 0) return {simulation:true, status:'NO_SITE_INTERSECTION', eta_sec:null, discriminant};
        const root = Math.sqrt(discriminant); const roots = [(-b - root) / (2 * a), (-b + root) / (2 * a)].filter(value => value >= 0).sort((x, y) => x - y);
        if (!roots.length) return {simulation:true, status:'NO_FUTURE_INTERSECTION', eta_sec:null, discriminant};
        if (roots[0] > settings.eta_search_horizon_sec) return {simulation:true, status:'NO_SITE_INTERSECTION', eta_sec:null, discriminant};
        return {simulation:true, status:'OK', eta_sec:roots[0], discriminant};
    }
    function computeSiteApproachAssessment(current, site, velocity, predictions, motion, options = {}) {
        const settings = {...DEFAULTS, ...options};
        const currentDistance = haversineDistanceM(current, site);
        const predictionWithDistance = predictions.map(prediction => ({...prediction, distance_to_site_m:haversineDistanceM(prediction, site)}));
        const distanceAtFive = predictionWithDistance.find(item => item.horizon_sec === 5)?.distance_to_site_m ?? currentDistance;
        const distanceDeltaFive = distanceAtFive - currentDistance;
        const closingSpeed = computeRadialClosingSpeed(current, site, velocity);
        let trend = 'UNCERTAIN';
        if (motion.speed_mps < settings.minimum_motion_speed_mps) trend = 'STATIONARY';
        else if (distanceDeltaFive <= -settings.distance_trend_tolerance_m && closingSpeed >= settings.radial_speed_tolerance_mps) trend = 'APPROACHING';
        else if (distanceDeltaFive >= settings.distance_trend_tolerance_m && closingSpeed <= -settings.radial_speed_tolerance_mps) trend = 'DEPARTING';
        const cpa = computeClosestPointOfApproach(current, site, velocity, settings.eta_search_horizon_sec);
        const intersection = computeProtectedRadiusIntersection(current, site, velocity, settings);
        const cpaPosition = cpa.reliable && cpa.time_sec !== null
            ? localOffsetToLatLng(current, velocity.east_mps * cpa.time_sec, velocity.north_mps * cpa.time_sec)
            : null;
        const entryPosition = intersection.eta_sec !== null
            ? localOffsetToLatLng(current, velocity.east_mps * intersection.eta_sec, velocity.north_mps * intersection.eta_sec)
            : null;
        return {
            simulation:true,
            current_distance_m:currentDistance,
            predictions:predictionWithDistance,
            trend,
            closing_speed_mps:closingSpeed,
            distance_delta_5s_m:distanceDeltaFive,
            cpa:{...cpa, lat:cpaPosition?.lat ?? null, lng:cpaPosition?.lng ?? null},
            intersection:{...intersection, lat:entryPosition?.lat ?? null, lng:entryPosition?.lng ?? null}
        };
    }
    function emptyContract(current, site, reasons) {
        const currentDistance = validPosition(current) && validPosition(site) ? haversineDistanceM(current, site) : null;
        const protectedRadius = siteProtectedRadiusM(site);
        const approach = {simulation:true, predicted_closest_distance_m:null, predicted_closest_time_sec:null, predicted_closest_lat:null, predicted_closest_lng:null, simulated_eta_sec:null, eta_reason:reasons[0] || 'DATA_INSUFFICIENT', predicted_entry_lat:null, predicted_entry_lng:null};
        return {
            simulation:true, status:'DATA_INSUFFICIENT', status_reasons:[...new Set(reasons)], model:'CV',
            current:{simulation:true, lat:finite(current?.lat), lng:finite(current?.lng), speed_mps:null, heading_deg:null, heading_reliable:false, turn_rate_deg_s:null},
            site:{simulation:true, id:site?.id || null, name:site?.name || null, lat:finite(site?.lat), lng:finite(site?.lng), protected_radius_m:protectedRadius, current_distance_m:currentDistance, bearing_to_site_deg:validPosition(current)&&validPosition(site)?computeBearingToSite(current,site):null},
            motion:{simulation:true, trend:'UNCERTAIN', closing_speed_mps:null},
            predictions:[],
            approach,
            site_metrics:approach,
            display:{simulation:true, show_prediction:false, show_heading:false, show_eta:false, show_entry_point:false, show_closest_point:false, show_uncertainty:false}
        };
    }
    function computeSimulationPredictionTick(input) {
        const settings = {...DEFAULTS, ...(input?.options || {})};
        const site = input?.site || {}; const history = input?.history || [];
        const quality = evaluatePredictionDataQuality(history, {...settings, position_uncertainty_m:input?.position_uncertainty_m});
        const current = validPosition(input?.current_position) ? {simulation:true, lat:Number(input.current_position.lat), lng:Number(input.current_position.lng)} : quality.points[quality.points.length - 1];
        const reasons = [...quality.status_reasons];
        if (!validPosition(site) || !(siteProtectedRadiusM(site) > 0)) reasons.push('INVALID_POSITION');
        if (!validPosition(current)) reasons.push('INVALID_POSITION');
        if (reasons.length) return emptyContract(current, site, reasons);
        const motion = estimateMotionState(quality.points, settings);
        if (!motion) return emptyContract(current, site, ['TOO_FEW_POINTS']);
        const headingReliable = motion.speed_mps > settings.minimum_motion_speed_mps;
        if (!headingReliable) return {...emptyContract(current, site, ['LOW_SPEED']), current:{simulation:true, lat:current.lat, lng:current.lng, speed_mps:motion.speed_mps, heading_deg:motion.heading_deg, heading_reliable:false, turn_rate_deg_s:motion.turn_rate_deg_s}, motion:{simulation:true, trend:'STATIONARY', closing_speed_mps:0}};
        const velocity = {east_mps:motion.east_mps, north_mps:motion.north_mps};
        const horizons = Array.isArray(input?.horizons_sec) ? input.horizons_sec : DEFAULT_HORIZONS_SEC;
        const rawPredictions = projectConstantVelocity(current, velocity, horizons);
        const siteAssessment = computeSiteApproachAssessment(current, site, velocity, rawPredictions, motion, settings);
        const bearing = computeBearingToSite(current, site);
        const etaMathematicallyExists = ['OK','AT_SITE'].includes(siteAssessment.intersection.status);
        const etaGate = siteAssessment.intersection.status === 'AT_SITE' || (
            siteAssessment.trend === 'APPROACHING' && siteAssessment.closing_speed_mps > settings.radial_speed_tolerance_mps && etaMathematicallyExists
        );
        let etaReason = siteAssessment.intersection.status;
        if (etaMathematicallyExists && !etaGate) etaReason = siteAssessment.trend === 'DEPARTING' ? 'DEPARTING' : 'TREND_UNCERTAIN';
        const approach = {
            simulation:true,
            predicted_closest_distance_m:siteAssessment.cpa.distance_m,
            predicted_closest_time_sec:siteAssessment.cpa.time_sec,
            predicted_closest_lat:siteAssessment.cpa.lat,
            predicted_closest_lng:siteAssessment.cpa.lng,
            simulated_eta_sec:etaGate?siteAssessment.intersection.eta_sec:null,
            eta_reason:etaReason,
            predicted_entry_lat:etaGate?siteAssessment.intersection.lat:null,
            predicted_entry_lng:etaGate?siteAssessment.intersection.lng:null
        };
        return {
            simulation:true, status:'OK', status_reasons:[], model:'CV',
            current:{simulation:true, lat:current.lat, lng:current.lng, speed_mps:motion.speed_mps, heading_deg:motion.heading_deg, heading_reliable:headingReliable, turn_rate_deg_s:motion.turn_rate_deg_s},
            site:{simulation:true, id:site.id, name:site.name, lat:Number(site.lat), lng:Number(site.lng), protected_radius_m:siteProtectedRadiusM(site), current_distance_m:siteAssessment.current_distance_m, bearing_to_site_deg:bearing},
            motion:{simulation:true, trend:siteAssessment.trend, closing_speed_mps:siteAssessment.closing_speed_mps},
            predictions:siteAssessment.predictions,
            approach,
            site_metrics:approach,
            display:{simulation:true, show_prediction:true, show_heading:true, show_eta:etaGate, show_entry_point:siteAssessment.intersection.status === 'OK' && etaGate && approach.predicted_entry_lat !== null, show_closest_point:siteAssessment.cpa.reliable && siteAssessment.cpa.time_sec > 0, show_uncertainty:finite(input?.position_uncertainty_m)!==null}
        };
    }

    root.DashboardSimulationPrediction = Object.freeze({
        EARTH_RADIUS_M, DEFAULT_HORIZONS_SEC, DEFAULTS,
        normalizeHeadingDeg, circularDifferenceDeg, localOffsetMeters,
        localOffsetToLatLng, haversineDistanceM, computeBearingToSite,
        bearingToSiteDeg:computeBearingToSite,
        velocityFromSpeedHeading, speedHeadingFromVelocity,
        normalizeSimulationHistory, unwrapHeadings, estimateTurnRate,
        evaluatePredictionDataQuality, estimateMotionState,
        projectConstantVelocity, projectConstantTurn,
        computeRadialClosingSpeed, computeClosingSpeed:computeRadialClosingSpeed,
        computeClosestPointOfApproach, computeCPA:computeClosestPointOfApproach,
        computeProtectedRadiusIntersection,
        computeSimulationSiteMetrics:computeSiteApproachAssessment,
        computeSiteApproachAssessment,
        computeSimulationPredictionTick
    });
})(typeof window === 'object' ? window : globalThis);
