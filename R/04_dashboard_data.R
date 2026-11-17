# Data for the dashboard (docs/index.html): writes docs/dashboard_data.js from output/.
# Open docs/index.html in a browser afterwards; on GitHub Pages it is the site's front page.

library(jsonlite)
ind <- read.csv("output/daily_indicator.csv")
waves <- read.csv("output/heat_waves.csv")
bt <- read.csv("output/backtest.csv")
settings <- read.csv("output/settings.txt", sep = " ", header = FALSE)

daily <- list(
  date = ind$date, calls = ind$heat_calls, tmax = ind$tmax, day_type = ind$day_type,
  expected = round(ind$expected_normal_tmax, 2), upper = ind$upper_limit,
  expected_actual = round(ind$expected_actual_tmax, 2),
  alarms = list(indicator = ind$alarm_indicator, farrington = ind$alarm_farrington,
                ears_c1 = ind$alarm_ears_c1, ears_c2 = ind$alarm_ears_c2, ears_c3 = ind$alarm_ears_c3)
)
data <- list(daily = daily, waves = waves, backtest = bt,
             settings = setNames(as.list(settings$V2), settings$V1))
writeLines(paste0("window.EMS = ", toJSON(data, dataframe = "rows", auto_unbox = TRUE, digits = NA), ";"),
           "docs/dashboard_data.js")
cat("wrote docs/dashboard_data.js\n")
