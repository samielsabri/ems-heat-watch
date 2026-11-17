# Heat indicator and back-test.
#
# Indicator: each week, fit a Poisson model (quasi-Poisson dispersion) to the previous 3 years of daily
# HEAT calls: trend + seasonal harmonics + day of week + temperature above a threshold T0 (same day,
# day before, mean of days 2-3). Predict the coming week twice: with the observed temperature, and with
# the normal temperature for each calendar day. Alarm when calls exceed the 99.5% upper limit of the
# normal-temperature expectation, i.e. more heat calls than a normal day at this time of year would give.
#
# Comparison: Farrington Flexible and EARS C1-C3 from the 'surveillance' package, on the same series.
#
# Back-test: heat waves = 3+ consecutive days with Tmax >= 32.2 C (90 F). Development 2016-2024, held out
# 2025 onwards (nothing was tuned on it). Mar-Jul 2020 (COVID) is left out of fitting and scoring.

suppressMessages({library(splines); library(surveillance)})
dir.create("output", showWarnings = FALSE)

heat <- read.csv("data/heat_calls.csv", colClasses = c("Date", "integer"))
tm <- read.csv("data/tmax.csv", colClasses = c("Date", "numeric"))
temp <- setNames(tm$tmax, format(tm$date))
Tmax <- function(dates) unname(temp[format(dates)])

alpha <- 0.005
train_end <- as.Date("2024-12-31")
eval_start <- as.Date("2016-01-01")
heldout_start <- as.Date("2025-01-01")
covid <- function(d) d >= as.Date("2020-03-01") & d <= as.Date("2020-07-31")

heat_terms <- function(dates, tfun, T0) {
  pos <- function(d) pmax(tfun(d) - T0, 0)
  data.frame(h0 = pos(dates), h1 = pos(dates - 1), h23 = (pos(dates - 2) + pos(dates - 3)) / 2)
}

# 1. Heat threshold T0: the value that best fits 2013-2024 (profile deviance, smooth time trend).
fit_years <- heat[heat$date >= as.Date("2013-01-01") & heat$date <= train_end & !covid(heat$date), ]
tt <- as.numeric(fit_years$date - min(fit_years$date)) / 365.25
dev_for <- function(T0) {
  x <- cbind(fit_years, heat_terms(fit_years$date, Tmax, T0), dow = weekdays(fit_years$date))
  deviance(glm(heat_calls ~ ns(tt, df = round(7 * max(tt))) + dow + h0 + h1 + h23, poisson, data = x))
}
grid <- seq(15, 33, by = 0.5)
T0 <- grid[which.min(sapply(grid, dev_for))]

# 2. Normal Tmax for each calendar day: 3 harmonics fitted to Tmax up to 2024.
harm <- function(d) {
  a <- 2 * pi * as.numeric(format(d, "%j")) / 365.25
  data.frame(s1 = sin(a), c1 = cos(a), s2 = sin(2 * a), c2 = cos(2 * a), s3 = sin(3 * a), c3 = cos(3 * a))
}
tn <- tm[tm$date <= train_end, ]
normal_fit <- lm(tmax ~ ., data = cbind(tmax = tn$tmax, harm(tn$date)))
Tnormal <- function(dates) unname(predict(normal_fit, harm(dates)))

# 3. Prospective indicator, refitted every 7 days on the previous 3 years.
design <- function(dates, origin, tfun) {
  cbind(trend = as.numeric(dates - origin) / 365.25, harm(dates),
        dow = factor(weekdays(dates), levels = weekdays(as.Date("2024-01-01") + 0:6)),
        heat_terms(dates, tfun, T0))
}
upper <- function(mu, phi) if (phi > 1) qnbinom(1 - alpha, size = mu / (phi - 1), mu = mu) else qpois(1 - alpha, mu)

blocks <- seq(eval_start, max(heat$date), by = 7)
ind <- do.call(rbind, lapply(blocks, function(d0) {
  train <- heat[heat$date >= seq(d0, by = "-3 years", length.out = 2)[2] & heat$date < d0 & !covid(heat$date), ]
  origin <- min(train$date)
  m <- glm(heat_calls ~ ., poisson, data = cbind(heat_calls = train$heat_calls, design(train$date, origin, Tmax)))
  phi <- sum(residuals(m, "pearson")^2) / df.residual(m)
  days <- seq(d0, min(d0 + 6, max(heat$date)), by = "day")
  mu_temp <- predict(m, design(days, origin, Tmax), type = "response")
  mu_norm <- predict(m, design(days, origin, Tnormal), type = "response")
  data.frame(date = days, expected_actual_tmax = mu_temp, expected_normal_tmax = mu_norm,
             upper_limit = sapply(mu_norm, upper, phi = phi))
}))
ind$heat_calls <- heat$heat_calls[match(ind$date, heat$date)]
ind$tmax <- Tmax(ind$date)
ind$alarm_indicator <- ind$heat_calls > ind$upper_limit

# 4. Standard aberration-detection methods on the same daily series.
s <- sts(observed = heat$heat_calls, epoch = as.numeric(heat$date), epochAsDate = TRUE, frequency = 365)
rng <- which(heat$date >= eval_start)
far <- farringtonFlexible(s, control = list(range = rng, b = 5, w = 7, noPeriods = 10, pastWeeksNotIncluded = 182,
                                            alpha = alpha, thresholdMethod = "nbPlugin", limit54 = c(5, 28)))
ind$alarm_farrington <- as.logical(alarms(far))
for (meth in c("C1", "C2", "C3")) {
  e <- earsC(s, control = list(range = rng, method = meth, baseline = 7, minSigma = 0.5, alpha = 0.001))
  ind[[paste0("alarm_ears_", tolower(meth))]] <- as.logical(alarms(e))
}

# 5. Score each method against heat waves.
hot <- tm$tmax >= 32.2
runs <- rle(hot)
ends <- cumsum(runs$lengths); starts <- ends - runs$lengths + 1
w <- which(runs$values & runs$lengths >= 3)
waves <- data.frame(start = tm$date[starts[w]], end = tm$date[ends[w]], days = runs$lengths[w])
waves$peak_tmax <- mapply(function(a, b) max(tm$tmax[tm$date >= a & tm$date <= b]), waves$start, waves$end)
waves <- waves[waves$start >= eval_start & waves$end <= max(heat$date) & !covid(waves$start) & !covid(waves$end), ]

d <- ind$date
in_wave <- near_wave <- rep(FALSE, length(d))
for (i in seq_len(nrow(waves))) {
  in_wave <- in_wave | (d >= waves$start[i] & d <= waves$end[i])
  near_wave <- near_wave | (d >= waves$start[i] - 3 & d <= waves$end[i] + 7)
}
recent_max <- pmax(Tmax(d), Tmax(d - 1), Tmax(d - 2), Tmax(d - 3))
summer <- as.integer(format(d, "%m")) %in% 5:9
non_heat_day <- summer & recent_max < 29.4 & !near_wave & !covid(d)       # cool summer days
hot_single_day <- Tmax(d) >= 32.2 & !in_wave & !covid(d)                  # hot days outside heat waves

methods <- c(indicator = "alarm_indicator", farrington = "alarm_farrington",
             ears_c1 = "alarm_ears_c1", ears_c2 = "alarm_ears_c2", ears_c3 = "alarm_ears_c3")
periods <- list(development = c(eval_start, heldout_start - 1), heldout = c(heldout_start, max(d)))
backtest <- do.call(rbind, lapply(names(periods), function(p) do.call(rbind, lapply(names(methods), function(m) {
  a <- ind[[methods[[m]]]]
  lo <- periods[[p]][1]; hi <- periods[[p]][2]
  wv <- waves[waves$start >= lo & waves$end <= hi, ]
  first <- sapply(seq_len(nrow(wv)), function(i) {
    hit <- d[a & d >= wv$start[i] & d <= wv$end[i]]
    if (length(hit)) as.numeric(min(hit) - wv$start[i]) else NA
  })
  sel <- d >= lo & d <= hi
  data.frame(period = p, method = m, heat_waves = nrow(wv), detected = sum(!is.na(first)),
             median_days_to_alarm = median(first, na.rm = TRUE),
             false_alarms_per_summer = round(mean(a[sel & non_heat_day]) * 153, 2),
             hot_single_days_flagged = round(mean(a[sel & hot_single_day]), 3))
}))))

write.csv(ind, "output/daily_indicator.csv", row.names = FALSE)
write.csv(waves, "output/heat_waves.csv", row.names = FALSE)
write.csv(backtest, "output/backtest.csv", row.names = FALSE)
writeLines(c(paste("T0", T0), paste("data_to", max(heat$date)), paste("alpha", alpha)), "output/settings.txt")
cat("T0 =", T0, "C\n")
print(backtest, row.names = FALSE)
