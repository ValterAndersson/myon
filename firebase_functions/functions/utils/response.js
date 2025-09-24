function ok(res, data, meta) {
  return res.status(200).json({ success: true, data, meta });
}

function fail(res, code, message, details, http = 400) {
  return res.status(http).json({ success: false, error: { code, message, details } });
}

module.exports = { ok, fail };


