# Download the inputs:
#   data/heat_calls.csv  daily NYC EMS calls (NYC Open Data, 76xm-jjuj) with final call type HEAT, and
#                        heat-related calls not coded as heat (the "syndrome" below)
#   data/tmax.csv        daily maximum temperature at Central Park (NOAA GHCN-Daily, USW00094728)

library(jsonlite)
dir.create("data", showWarnings = FALSE)
start <- as.Date("2010-01-01")

# Heat-related presentations not coded as heat, chosen before looking at results: unconscious, altered mental
# status, sick, breathing difficulty, cardiac, cardiac/breathing, respiratory, cardiac arrest. NYC added variant
# codes to these families (e.g. SICKFC in 2020-23), so every variant is listed.
syndrome <- c("UNC", "ALTMEN", "SICK", "DIFFBR", "CARD", "CARDBR", "RESPIR", "ARREST",
              outer(c("UNC", "ALTM", "SICK", "DIFF", "CARD", "CDBR", "RESP", "ARRE"), c("FC", "RF", "FT"), paste0))

# The portal does the counting, so each request returns one row per day instead of millions of calls.
daily_count <- function(types) {
  url <- paste0(
    "https://data.cityofnewyork.us/resource/76xm-jjuj.json?",
    "$select=date_trunc_ymd(incident_datetime) as date, count(*) as n",
    "&$where=final_call_type in(", paste0("'", types, "'", collapse = ","), ") AND incident_datetime >= '",
    start, "T00:00:00'&$group=date&$order=date&$limit=50000")
  x <- fromJSON(URLencode(url))
  data.frame(date = as.Date(substr(x$date, 1, 10)), n = as.integer(x$n))
}
heat <- daily_count("HEAT")
other <- daily_count(syndrome)

# Days with no HEAT calls are missing from the query result, so fill them with 0
# up to the last day the portal has any data for.
latest <- fromJSON(URLencode(paste0(
  "https://data.cityofnewyork.us/resource/76xm-jjuj.json?$select=max(incident_datetime) as latest")))
# the last day counts as complete only if the latest record is from late evening
last_time <- as.POSIXct(substr(latest$latest, 1, 19), format = "%Y-%m-%dT%H:%M:%S", tz = "UTC")
last_day <- as.Date(last_time) - ifelse(format(last_time, "%H") >= "23", 0, 1)
days <- data.frame(date = seq(start, last_day, by = "day"))
heat <- merge(merge(days, heat, all.x = TRUE), setNames(other, c("date", "syndrome_calls")), all.x = TRUE)
names(heat)[2] <- "heat_calls"
heat[is.na(heat)] <- 0L
write.csv(heat, "data/heat_calls.csv", row.names = FALSE)

noaa <- read.csv("https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/USW00094728.csv")
tmax <- data.frame(date = as.Date(noaa$DATE), tmax = noaa$TMAX / 10)   # tenths of a degree C
tmax <- tmax[tmax$date >= start - 7 & !is.na(tmax$tmax), ]
write.csv(tmax, "data/tmax.csv", row.names = FALSE)

cat("heat calls:", format(min(heat$date)), "to", format(max(heat$date)), "-", sum(heat$heat_calls), "calls\n")
cat("syndrome:  ", sum(heat$syndrome_calls), "calls\n")
cat("tmax:      ", format(min(tmax$date)), "to", format(max(tmax$date)), "\n")
