# Homebrew formula. After each PyPI sdist, fill url + sha256:
#   curl -sL https://pypi.org/pypi/installgate/json | python3 -c \
#     "import json,sys; d=json.load(sys.stdin)['urls']; u=[x for x in d if x['packagetype']=='sdist'][0]; print(u['url']); print(u['digests']['sha256'])"
class Installgate < Formula
  desc "Pre-install trust gate for pip and npm"
  homepage "https://github.com/Seavleu/installgate"
  url "https://files.pythonhosted.org/packages/source/i/installgate/installgate-0.1.3.tar.gz"
  sha256 "REPLACE_AFTER_RELEASE"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "installgate", shell_output("#{bin}/ig --version")
  end
end
