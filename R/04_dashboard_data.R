# Data for the dashboard: writes docs/dashboard_data.js from output/.
# docs/ is published by GitHub Pages at https://samielsabri.me/ems-heat-watch/ - push to main and it is live.

library(jsonlite)
ind <- read.csv("output/daily_indicator.csv")
waves <- read.csv("output/heat_waves.csv")
bt <- read.csv("output/backtest.csv")
burden <- read.csv("output/hidden_burden_by_wave.csv")
burden_summary <- read.csv("output/hidden_burden.csv")
settings <- read.csv("output/settings.txt", sep = " ", header = FALSE)

daily <- list(
  date = ind$date, calls = ind$heat_calls, tmax = ind$tmax, day_type = ind$day_type,
  expected = round(ind$expected_normal_tmax, 2), upper = ind$upper_limit,
  expected_actual = round(ind$expected_actual_tmax, 2),
  alarms = list(indicator = ind$alarm_indicator, farrington = ind$alarm_farrington,
                ears_c1 = ind$alarm_ears_c1, ears_c2 = ind$alarm_ears_c2, ears_c3 = ind$alarm_ears_c3)
)
burden[, 3:6] <- round(burden[, 3:6])
data <- list(daily = daily, waves = waves, backtest = bt, burden = burden, burden_summary = burden_summary,
             settings = setNames(as.list(settings$V2), settings$V1))
js <- paste0("window.EMS = ", toJSON(data, dataframe = "rows", auto_unbox = TRUE, digits = NA), ";")
writeLines(js, "docs/dashboard_data.js")
cat("wrote docs/dashboard_data.js\n")
