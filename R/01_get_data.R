# Download the two inputs:
#   data/heat_calls.csv  daily count of NYC EMS calls with final call type HEAT (NYC Open Data, 76xm-jjuj)
#   data/tmax.csv        daily maximum temperature at Central Park (NOAA GHCN-Daily, USW00094728)

library(jsonlite)
dir.create("data", showWarnings = FALSE)
start <- as.Date("2010-01-01")

# The portal does the counting, so this is one small request instead of 20 million rows.
url <- paste0(
  "https://data.cityofnewyork.us/resource/76xm-jjuj.json?",
  "$select=date_trunc_ymd(incident_datetime) as date, count(*) as n",
  "&$where=final_call_type='HEAT' AND incident_datetime >= '", start, "T00:00:00'",
  "&$group=date&$order=date&$limit=50000"
)
heat <- fromJSON(URLencode(url))
heat$date <- as.Date(substr(heat$date, 1, 10))
heat$n <- as.integer(heat$n)

# Days with no HEAT calls are missing from the query result, so fill them with 0
# up to the last day the portal has any data for.
latest <- fromJSON(URLencode(paste0(
  "https://data.cityofnewyork.us/resource/76xm-jjuj.json?$select=max(incident_datetime) as latest")))
# the last day counts as complete only if the latest record is from late evening
last_time <- as.POSIXct(substr(latest$latest, 1, 19), format = "%Y-%m-%dT%H:%M:%S", tz = "UTC")
last_day <- as.Date(last_time) - ifelse(format(last_time, "%H") >= "23", 0, 1)
days <- data.frame(date = seq(start, last_day, by = "day"))
heat <- merge(days, heat, all.x = TRUE)
heat$n[is.na(heat$n)] <- 0L
names(heat)[2] <- "heat_calls"
write.csv(heat, "data/heat_calls.csv", row.names = FALSE)

noaa <- read.csv("https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/USW00094728.csv")
tmax <- data.frame(date = as.Date(noaa$DATE), tmax = noaa$TMAX / 10)   # tenths of a degree C
tmax <- tmax[tmax$date >= start - 7 & !is.na(tmax$tmax), ]
write.csv(tmax, "data/tmax.csv", row.names = FALSE)

cat("heat calls:", format(min(heat$date)), "to", format(max(heat$date)), "-", sum(heat$heat_calls), "calls\n")
cat("tmax:      ", format(min(tmax$date)), "to", format(max(tmax$date)), "\n")
