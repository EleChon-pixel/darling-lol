/*
 * Guest-side M7 SIP prototype test: protected-path writes, /usr/local
 * exception, symlink/.. escapes and csrctl's active configuration.
 *
 * An optional "vfs" argument exercises the remaining mutating wrappers and
 * the dev/inode hardlink check. It must only run with SIP on.
 */

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/attr.h>
#include <sys/csr.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/xattr.h>

static int try_mkdir(const char* path) {
	int rc = mkdir(path, 0700);
	int error = errno;
	printf("mkdir %s rc=%d errno=%d\n", path, rc, error);
	if (rc == 0)
		rmdir(path);
	return rc == 0 ? 0 : error;
}

static int try_write(const char* path) {
	int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
	if (fd < 0) {
		int error = errno;
		printf("write %s rc=-1 errno=%d\n", path, error);
		return error;
	}
	close(fd);
	printf("write %s rc=0\n", path);
	return 0;
}

static int expect_eperm(const char* label, int rc, int error) {
	if (rc == -1 && error == EPERM)
		return 0;
	printf("VFS_FAIL %s rc=%d errno=%d\n", label, rc, error);
	return 1;
}

static int test_vfs(void) {
	int failures = 0;
	int fd, rc, error;
	filesec_t filesec;
	uid_t uid = getuid();
	gid_t gid = getgid();
	mode_t mode = 0644;
	struct attrlist attrs = {
		.bitmapcount = ATTR_BIT_MAP_COUNT,
		.commonattr = ATTR_CMN_ACCESSMASK,
	};
	uint32_t access_mode = 0644;

	rc = chmod("/private/etc", 0755); error = errno;
	failures += expect_eperm("chmod", rc, error);
	rc = chown("/private/etc", 0, 0); error = errno;
	failures += expect_eperm("chown", rc, error);
	rc = utimes("/private/etc", NULL); error = errno;
	failures += expect_eperm("utimes", rc, error);
	rc = setxattr("/private/etc", "user.sip-test", "x", 1, 0, 0); error = errno;
	failures += expect_eperm("setxattr", rc, error);
	rc = removexattr("/private/etc/sip-file", "user.sip-remove", 0); error = errno;
	failures += expect_eperm("removexattr", rc, error);
	rc = truncate("/private/etc/sip-file", 0); error = errno;
	failures += expect_eperm("truncate", rc, error);
	rc = rmdir("/private/etc"); error = errno;
	failures += expect_eperm("rmdir", rc, error);
	rc = symlink("/tmp", "/private/etc/sip-newlink"); error = errno;
	failures += expect_eperm("symlink", rc, error);
	rc = link("/private/etc/sip-file", "/private/tmp/sip-hardlink"); error = errno;
	failures += expect_eperm("link", rc, error);

	fd = open("/private/etc/sip-file", O_RDONLY);
	if (fd < 0) {
		printf("VFS_FAIL open-protected rc=-1 errno=%d\n", errno);
		return failures + 1;
	}
	rc = fchmod(fd, 0644); error = errno;
	failures += expect_eperm("fchmod", rc, error);
	rc = ftruncate(fd, 0); error = errno;
	failures += expect_eperm("ftruncate", rc, error);
	rc = futimes(fd, NULL); error = errno;
	failures += expect_eperm("futimes", rc, error);
	rc = fsetxattr(fd, "user.sip-test", "x", 1, 0, 0); error = errno;
	failures += expect_eperm("fsetxattr", rc, error);
	rc = fremovexattr(fd, "user.sip-remove", 0); error = errno;
	failures += expect_eperm("fremovexattr", rc, error);

	filesec = filesec_init();
	if (filesec == NULL ||
	    filesec_set_property(filesec, FILESEC_OWNER, &uid) != 0 ||
	    filesec_set_property(filesec, FILESEC_GROUP, &gid) != 0 ||
	    filesec_set_property(filesec, FILESEC_MODE, &mode) != 0) {
		printf("VFS_FAIL filesec setup errno=%d\n", errno);
		failures++;
	} else {
		rc = chmodx_np("/private/etc/sip-file", filesec); error = errno;
		failures += expect_eperm("chmodx_np", rc, error);
		rc = fchmodx_np(fd, filesec); error = errno;
		failures += expect_eperm("fchmodx_np", rc, error);
	}
	if (filesec != NULL)
		filesec_free(filesec);

	rc = setattrlist("/private/etc/sip-file", &attrs, &access_mode,
	    sizeof(access_mode), 0); error = errno;
	failures += expect_eperm("setattrlist", rc, error);
	rc = fsetattrlist(fd, &attrs, &access_mode, sizeof(access_mode), 0); error = errno;
	failures += expect_eperm("fsetattrlist", rc, error);
	{
		/* A writable MAP_PRIVATE mapping is copy-on-write and does not
		 * modify the protected file, so SIP must allow it. */
		void* mapping = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE, fd, 0);
		error = errno;
		if (mapping == MAP_FAILED) {
			printf("VFS_FAIL mmap-private rc=-1 errno=%d\n", error);
			failures++;
		} else {
			munmap(mapping, 4096);
		}

		/* MAP_SHARED can modify the protected file, so SIP must refuse it
		 * before the kernel returns its own EACCES for the read-only fd. */
		mapping = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
		error = errno;
		failures += expect_eperm("mmap-shared", mapping == MAP_FAILED ? -1 : 0, error);
		if (mapping != MAP_FAILED)
			munmap(mapping, 4096);
	}
	close(fd);

	rc = mkfifo("/private/etc/sip-fifo", 0600); error = errno;
	failures += expect_eperm("mkfifo", rc, error);
	if (rc == 0)
		unlink("/private/etc/sip-fifo");
	rc = mknod("/private/etc/sip-node", S_IFIFO | 0600, 0); error = errno;
	failures += expect_eperm("mknod", rc, error);
	if (rc == 0)
		unlink("/private/etc/sip-node");

	/* Seed the inode registry through the protected path, then prove that a
	 * pre-existing hardlink outside the protected tree is refused by dev/ino. */
	fd = open("/private/etc/sip-inode", O_WRONLY);
	error = errno;
	failures += expect_eperm("seed-protected-open", fd == -1 ? -1 : 0, error);
	if (fd >= 0)
		close(fd);
	fd = open("/private/tmp/sip-inode-link", O_WRONLY);
	error = errno;
	failures += expect_eperm("hardlink-open", fd == -1 ? -1 : 0, error);
	if (fd >= 0) {
		close(fd);
		unlink("/private/tmp/sip-inode-link");
	}

	fd = open("/usr/local/sip-inode-link", O_WRONLY);
	error = errno;
	failures += expect_eperm("hardlink-usr-local-open", fd == -1 ? -1 : 0, error);
	if (fd >= 0)
		close(fd);

	if (failures == 0) {
		printf("SIP_VFS_OK\n");
		return 0;
	}
	printf("SIP_VFS_FAIL failures=%d\n", failures);
	return 1;
}

int main(int argc, char** argv) {
	csr_config_t config = 0xffffffffu;
	int protected_write, protected_mkdir, local_write, dotdot_write, localdotdot_write, symlink_write;

	if (csr_get_active_config(&config) != 0) {
		printf("CSR_GET_FAIL errno=%d\n", errno);
		return 1;
	}
	printf("csr_config=0x%08x\n", config);
	if (config != 0 &&
	    setxattr("/private/etc/sip-file", "user.sip-remove", "x", 1, 0, 0) != 0) {
		printf("SIP_FAIL seed-removexattr errno=%d\n", errno);
		return 1;
	}

	if (argc > 1 && strcmp(argv[1], "vfs") == 0) {
		if (config != 0) {
			printf("SIP_VFS_SKIP\n");
			return 0;
		}
		return test_vfs();
	}

	protected_mkdir = try_mkdir("/private/etc/sip-newdir");
	protected_write = try_write("/private/etc/sip-test");
	local_write = try_write("/usr/local/sip-test");
	dotdot_write = try_write("/private/etc/../etc/sip-test");
	localdotdot_write = try_write("/usr/local/../private/etc/sip-test");
	symlink_write = try_write("/private/tmp/sip-link/sip-test");

	unlink("/usr/local/sip-test");
	unlink("/private/etc/sip-test");

	if (config != 0) {
		if (protected_write != 0 || protected_mkdir != 0 || dotdot_write != 0 ||
		    localdotdot_write != 0 || symlink_write != 0 || local_write != 0) {
			printf("SIP_FAIL protected=%d mkdir=%d dotdot=%d localdotdot=%d symlink=%d local=%d\n",
			    protected_write, protected_mkdir, dotdot_write,
			    localdotdot_write, symlink_write, local_write);
			return 1;
		}
		printf("SIP_OFF_OK\n");
	} else {
		if (protected_write != EPERM || protected_mkdir != EPERM ||
		    dotdot_write != EPERM || localdotdot_write != EPERM ||
		    symlink_write != EPERM || local_write != 0) {
			printf("SIP_FAIL protected=%d mkdir=%d dotdot=%d localdotdot=%d symlink=%d local=%d\n",
			    protected_write, protected_mkdir, dotdot_write,
			    localdotdot_write, symlink_write, local_write);
			return 1;
		}
		printf("SIP_ON_OK\n");
	}
	return 0;
}
